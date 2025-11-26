# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Dict, List
import numpy as np
import yaml

class BiDirectionalPowerConverter(Protocol):
    id: str
    from_bus: str   # sens physique
    to_bus: str     # sens physique
    
    def forward(self, p_in_w: np.ndarray) -> np.ndarray:
        """Physique: from -> to  (ex: Genset: Chemical->Electrical)"""

    def inverse(self, p_out_w: np.ndarray) -> np.ndarray:
        """Inverse statique: to -> from  (ex: P_in = P_out / η_eff)"""


@dataclass
class ConstantEtaConverter:
    id: str
    from_bus: str
    to_bus: str
    eta: float
    p_in_max_w: float | None = None
    p_out_max_w: float | None = None

    def forward(self, p_in_w: np.ndarray) -> np.ndarray:
        p_in = np.asarray(p_in_w, float)
        if self.p_in_max_w is not None:
            p_in = np.minimum(p_in, self.p_in_max_w)
        p_out = p_in * float(self.eta)
        if self.p_out_max_w is not None:
            p_out = np.minimum(p_out, self.p_out_max_w)
        return p_out

    def inverse(self, p_out_w: np.ndarray) -> np.ndarray:
        p_out = np.asarray(p_out_w, float)
        if self.p_out_max_w is not None:
            # Si on demande plus que max, on sature: on ne peut produire que p_out_max
            p_out = np.minimum(p_out, self.p_out_max_w)
        # P_in = P_out / η
        eta = max(float(self.eta), 1e-12)
        p_in = p_out / eta
        if self.p_in_max_w is not None:
            p_in = np.minimum(p_in, self.p_in_max_w)
        return p_in


@dataclass
class TabulatedEtaConverter:
    id: str
    from_bus: str
    to_bus: str
    # table (entrée physique p_in) -> η
    p_in_grid_w: np.ndarray         # ex: [0, 100e3, 200e3, ...]
    eta_grid:    np.ndarray         # même taille
    p_in_max_w:  float

    def _eta(self, p_in: np.ndarray) -> np.ndarray:
        p = np.clip(p_in, self.p_in_grid_w.min(), self.p_in_grid_w.max())
        return np.interp(p, self.p_in_grid_w, self.eta_grid)

    def forward(self, p_in_w: np.ndarray) -> np.ndarray:
        p_in = np.minimum(np.asarray(p_in_w,float), self.p_in_max_w)
        return p_in * self._eta(p_in)

    def inverse(self, p_out_w: np.ndarray) -> np.ndarray:
        # résout point-par-point: p_out = eta(p_in)*p_in
        p_out = np.asarray(p_out_w, float)
        p_in  = np.zeros_like(p_out)

        lo = np.zeros_like(p_out)
        hi = np.full_like(p_out, self.p_in_max_w)

        # si p_out dépasse le max atteignable, on sature
        p_out_max = self.forward(hi)
        mask_sat = p_out >= (p_out_max - 1e-9)
        p_in[mask_sat] = hi[mask_sat]

        # bisection pour le reste
        mask = ~mask_sat
        for _ in range(30):
            mid = 0.5*(lo[mask] + hi[mask])
            f_mid = self.forward(mid) - p_out[mask]
            # on veut f_mid >= 0 ⇒ hi = mid ; else lo = mid
            hi[mask] = np.where(f_mid >= 0, mid, hi[mask])
            lo[mask] = np.where(f_mid <  0, mid, lo[mask])
            if np.max(hi[mask]-lo[mask]) < 1e-6:
                break
        p_in[mask] = 0.5*(lo[mask] + hi[mask])
        return p_in


@dataclass
class Runner:
    mode: str  # "inverse" ou "forward"
    buses: Dict[str, Bus]          # Bus.net[t] signé (+ injecte, − demande)
    converters: List[BiDirectionalConverter]
    # dag: edges physiques (from_bus -> to_bus)

    def run(self):
        if self.mode == "inverse":
            order = reversed(list(nx.topological_sort(self.dag)))
            for to_bus in order:
                for _, from_bus, data in self.dag.out_edges(to_bus, data=True):
                    conv = data["conv"]  # instance BiDirectionalConverter
                    need = -np.minimum(0.0, self.buses[to_bus].net_W)  # demande ≥ 0
                    if np.any(need > 0):
                        p_in = conv.inverse(need)
                        self.buses[to_bus].add(f"from:{conv.id}", +need)
                        self.buses[from_bus].add(f"to:{conv.id}",   -p_in)

        elif self.mode == "forward":
            order = list(nx.topological_sort(self.dag))
            for from_bus in order:
                for _, to_bus, data in self.dag.out_edges(from_bus, data=True):
                    conv = data["conv"]
                    # ici, il te faut une politique pour "pousser" p_in (ex: tout le surplus du from_bus)
                    surplus = np.maximum(0.0, self.buses[from_bus].net_W)
                    if np.any(surplus > 0):
                        p_out = conv.forward(surplus)
                        self.buses[from_bus].add(f"via:{conv.id}", -surplus)
                        self.buses[to_bus].add(f"from:{conv.id}",  +p_out)
        else:
            raise ValueError("mode must be 'inverse' or 'forward'")


if __name__ == "__main__":
    # horizon (vectoriel)
    dt = 1.0
    T  = 20
    t  = np.arange(0.0, T*dt, dt)
    
    # YAML minimal
    cfg_txt = """
solver:
  mode: "inverse"   # ou "forward"
  
buses:
  - {id: "Mechanical:shaft", carrier: "Mechanical"}
  - {id: "Electrical:main",  carrier: "Electrical"}
  - {id: "Chemical:fuel",    carrier: "Chemical"}

inputs:
  - {id: "shaft_demand", bus: "Mechanical:shaft", p_const_W: -150000.0} # demande méca
  - {id: "navops",       bus: "Electrical:main",  p_const_W:  -20000.0} # demande élec

converters:
  - id: "genset"
    type: "constant_eta"
    from: "Chemical:fuel"      # physique (amont)
    to:   "Electrical:main"     # physique (aval)
    eta:  0.45

  - id: "motor"
    type: "tab_eta"
    from: "Electrical:main"
    to:   "Mechanical:shaft"
    p_in_grid_w: [0, 100000, 300000, 600000, 800000]
    eta_grid:    [0.60, 0.75, 0.86, 0.88, 0.87]
    p_in_max_w:  800000
"""
    cfg = yaml.safe_load(cfg_txt)




