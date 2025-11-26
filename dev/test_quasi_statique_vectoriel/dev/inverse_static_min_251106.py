# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Dict, List, Tuple
import numpy as np
import yaml  # pip install pyyaml

# -----------------------------
# Protocols (interfaces simples)
# -----------------------------
class SupportsLoad(Protocol):
    def demand_series(self, t: np.ndarray) -> np.ndarray: ...

class SupportsSource(Protocol):
    def supply_series(self, t: np.ndarray) -> np.ndarray: ...

class SupportsConverter(Protocol):
    id: str
    from_bus: str
    to_bus: str
    def run_inverse(self, buses: Dict[str, "Bus"]) -> None: ...
    # doit remplir ses propres séries et mettre à jour le bus amont


# -----------------------------
# Bus (porte un profil de P[t])
# Convention : P[t] en W (demande nette sur le bus)
# -----------------------------
@dataclass
class Bus:
    id: str
    carrier: str
    P: np.ndarray  # profil (W), positif = demande
    # “journal” pour visualiser d’où vient la demande
    ledger: Dict[str, np.ndarray] = field(default_factory=dict)

    def add_demand(self, label: str, series_W: np.ndarray):
        self.P = self.P + series_W
        if label not in self.ledger:
            self.ledger[label] = np.zeros_like(self.P)
        self.ledger[label] = self.ledger[label] + series_W


# -----------------------------
# Inputs (sources de demande)
# -----------------------------
@dataclass
class SpeedToShaft:
    """v(t) -> P_shaft(t) via table (linéaire clamp) ; ajoute sur bus mécanique."""
    bus_id: str
    map_v_to_pshaft: List[Tuple[float, float]]  # [(m/s, W), ...]
    v_profile: np.ndarray  # m/s

    def demand_series(self, t: np.ndarray) -> np.ndarray:
        xp = np.array([v for v, _ in self.map_v_to_pshaft], dtype=float)
        fp = np.array([p for _, p in self.map_v_to_pshaft], dtype=float)
        v = np.asarray(self.v_profile, dtype=float)
        v = np.clip(v, xp.min(), xp.max())
        return np.interp(v, xp, fp)  # W

@dataclass
class NavOps:
    """Profil électrique (W >0 = demande)."""
    bus_id: str
    profile_W: np.ndarray
    def demand_series(self, t: np.ndarray) -> np.ndarray:
        return np.asarray(self.profile_W, dtype=float)


# -----------------------------
# Convertisseurs “inverse statique” (η constant)
# -----------------------------
@dataclass
class MotorInverse:
    """Méca (sortie) -> Elec (entrée) : P_elec = P_shaft / η."""
    id: str
    from_bus: str  # Electrical
    to_bus: str    # Mechanical (où se trouve la demande P_shaft)
    eta: float
    # séries stockées pour debug
    pout_W: np.ndarray = field(default=None, init=False)  # côté aval (to_bus)
    pin_W:  np.ndarray = field(default=None, init=False)  # côté amont (from_bus)

    def run_inverse(self, buses: Dict[str, Bus]) -> None:
        b_out = buses[self.to_bus]
        b_in  = buses[self.from_bus]
        P_shaft = b_out.P  # tout ce qui est sur le bus méca doit être couvert
        P_elec  = np.divide(P_shaft, max(self.eta, 1e-9))
        # journaliser
        self.pout_W = P_shaft.copy()
        self.pin_W  = P_elec.copy()
        b_in.add_demand(f"from:{self.id}", P_elec)

@dataclass
class GensetInverse:
    """Élec (sortie) -> Chim (entrée) : P_chem = P_elec / η."""
    id: str
    from_bus: str  # Chemical (fuel)
    to_bus: str    # Electrical (demande totale élec)
    eta: float
    pout_W: np.ndarray = field(default=None, init=False)
    pin_W:  np.ndarray = field(default=None, init=False)

    def run_inverse(self, buses: Dict[str, Bus]) -> None:
        b_out = buses[self.to_bus]
        b_in  = buses[self.from_bus]
        P_elec = b_out.P
        P_chem = np.divide(P_elec, max(self.eta, 1e-9))
        self.pout_W = P_elec.copy()
        self.pin_W  = P_chem.copy()
        b_in.add_demand(f"from:{self.id}", P_chem)


# -----------------------------
# Orchestrateur minimal (DAG simple)
# -----------------------------
@dataclass
class InverseStaticRunner:
    t: np.ndarray
    buses: Dict[str, Bus]
    inputs: List[SupportsLoad]
    converters: List[SupportsConverter]

    @classmethod
    def from_yaml(cls, cfg: dict, t: np.ndarray) -> "InverseStaticRunner":
        # 1) Buses
        buses: Dict[str, Bus] = {}
        for b in cfg["buses"]:
            buses[b["id"]] = Bus(id=b["id"], carrier=b["carrier"], P=np.zeros_like(t, dtype=float))

        # 2) Inputs
        inputs: List[SupportsLoad] = []
        for src in cfg["inputs"]:
            if src["type"] == "speed_profile":
                # profil vitesse: soit fourni, soit synthétique (const/rampe)
                if "v_profile" in src:
                    v = np.array(src["v_profile"], dtype=float)
                else:
                    v = np.full_like(t, fill_value=float(src.get("v_const", 0.0)), dtype=float)
                inputs.append(SpeedToShaft(
                    bus_id=src["bus"],
                    map_v_to_pshaft=[tuple(x) for x in src["map_v_to_pshaft"]],
                    v_profile=v
                ))
            elif src["type"] == "navops_profile":
                if "profile_W" in src:
                    p = np.array(src["profile_W"], dtype=float)
                else:
                    p = np.full_like(t, fill_value=float(src.get("p_const_W", 0.0)), dtype=float)
                inputs.append(NavOps(bus_id=src["bus"], profile_W=p))
            else:
                raise ValueError(f"Unknown input type: {src['type']}")

        # 3) Converters
        converters: List[SupportsConverter] = []
        for cv in cfg["converters"]:
            if cv["type"] == "motor_inverse":
                converters.append(MotorInverse(
                    id=cv["id"], from_bus=cv["from_bus"], to_bus=cv["to_bus"], eta=float(cv["eta"])
                ))
            elif cv["type"] == "genset_inverse":
                converters.append(GensetInverse(
                    id=cv["id"], from_bus=cv["from_bus"], to_bus=cv["to_bus"], eta=float(cv["eta"])
                ))
            else:
                raise ValueError(f"Unknown converter type: {cv['type']}")

        return cls(t=t, buses=buses, inputs=inputs, converters=converters)

    def apply_inputs(self):
        # remet les P à zéro, puis applique les inputs (qui ADD sur leur bus)
        for b in self.buses.values():
            b.P[:] = 0.0
            b.ledger.clear()
        for src in self.inputs:
            series = src.demand_series(self.t)
            # retrouve le bus id (attribué dans l'objet source)
            bus_id = getattr(src, "bus_id")
            self.buses[bus_id].add_demand(type(src).__name__, series)

    def run(self):
        """Ordre d’exécution DAG : ici trivial (motor d’abord pour propulser la demande vers élec,
        puis genset pour remonter vers chimique). Dans un cas général, tu peux calculer un tri topo
        sur un graphe (from_bus -> to_bus) et exécuter du plus “aval” vers l’amont.
        """
        self.apply_inputs()
        # 1) propager la demande méca -> élec
        for cv in self.converters:
            if isinstance(cv, MotorInverse):
                cv.run_inverse(self.buses)
        # 2) propager la demande élec -> chim
        for cv in self.converters:
            if isinstance(cv, GensetInverse):
                cv.run_inverse(self.buses)

    # Helpers debug
    def show_bus(self, bus_id: str, k: int = 0, every: int = 10):
        b = self.buses[bus_id]
        print(f"\n[BUS {bus_id}] carrier={b.carrier}")
        for label, s in b.ledger.items():
            print(f"  {label:16s}  sample[0:{every}:{k}] = {s[0:len(s):max(1,every)][:5]}")
        print(f"  TOTAL P[0:{every}:{k}] = {b.P[0:len(b.P):max(1,every)][:5]}")

# -----------------------------
# Demo (utilise le YAML plus bas)
# -----------------------------
if __name__ == "__main__":
    # horizon temporel
    dt = 1.0
    T  = 30
    t  = np.arange(0.0, T*dt, dt)

    # charge le YAML d’exemple (ci-dessous)
    with open("inverse_static_min.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    runner = InverseStaticRunner.from_yaml(cfg, t)

    # si aucun profil explicite n’est donné dans le YAML, on peut créer un v(t) simple ici :
    # (dans ce YAML d’exemple, on a mis v_const et p_const_W pour faire court)
    runner.run()

    # inspecte buses
    runner.show_bus("Mechanical:shaft")
    runner.show_bus("Electrical:main")
    runner.show_bus("Chemical:fuel")

    # exemples de valeurs scalaires
    P_shaft = runner.buses["Mechanical:shaft"].P
    P_elec  = runner.buses["Electrical:main"].P
    P_chem  = runner.buses["Chemical:fuel"].P
    print("\nExtrait:")
    for i in range(0, len(t), 10):
        print(f"t={t[i]:4.0f}s  P_shaft={P_shaft[i]/1e3:7.1f} kW  "
              f"P_elec={P_elec[i]/1e3:7.1f} kW  P_chem={P_chem[i]/1e3:7.1f} kW")
