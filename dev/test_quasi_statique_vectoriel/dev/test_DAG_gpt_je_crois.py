# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import numpy as np
import networkx as nx


# --------------- Core data ---------------
@dataclass
class Bus:
    id: str
    carrier: str
    net_W: np.ndarray  # signé: + injection ; - demande
    ledger: Dict[str, np.ndarray] = field(default_factory=dict)
    def add(self, label: str, series_W: np.ndarray):
        s = np.asarray(series_W, dtype=float)
        self.net_W = self.net_W + s
        self.ledger[label] = self.ledger.get(label, np.zeros_like(self.net_W)) + s

@dataclass
class SignedInput:
    """Profil signé appliqué à un bus."""
    id: str
    bus_id: str
    profile: np.ndarray
    def series(self, t: np.ndarray) -> np.ndarray:
        return np.asarray(self.profile, dtype=float)

@dataclass
class Converter:
    """Converter générique: from_bus --(η)--> to_bus."""
    id: str
    from_bus: str
    to_bus: str
    # logs
    p_out_W: np.ndarray = field(default=None, init=False)  # injection effectuée sur to_bus
    p_in_W:  np.ndarray = field(default=None, init=False)  # retrait appliqué sur from_bus



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