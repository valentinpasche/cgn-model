# cgn_model/vessel_model/base.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal
import copy, yaml

from numpy.typing import NDArray
import numpy as np

from cgn_model.energy_solver import SolverDAG

type FArray = NDArray[np.floating]
type SolverMode = Literal["forward", "inverse"]
type BEType = Literal["DE", "steam", "undefined"]

__all__ = ["Vessel"]

@dataclass
class Vessel:
    name: str
    be_type: BEType
    solver: SolverDAG

    @classmethod
    def from_yaml(cls, cfg: str | dict[str, Any]) -> "Vessel":
        vessel_meta = cls._parse_cfg(cfg)
        solver = SolverDAG.from_yaml(cfg)
        return cls(
            name=vessel_meta.get("name", "unknown"),
            be_type=vessel_meta.get("type", "undefined"),
            solver=solver,
        )

    @staticmethod
    def _parse_cfg(cfg: str | dict[str, Any]) -> dict[str, Any]:
        source = yaml.safe_load(cfg) if isinstance(cfg, str) else cfg
        if not isinstance(source, dict) or source is None:
            raise ValueError("La configuration YAML est vide ou n'est pas un mapping.")
        vessel = copy.deepcopy(source.get("vessel")) if isinstance(source.get("vessel"), dict) else {}

        # strip naïf
        for k, v in list(vessel.items()):
            if isinstance(v, str):
                vessel[k] = v.strip()

        vessel.setdefault("name", "unknown")
        vessel.setdefault("type", "undefined")
        return {"name": vessel.get("name"), "type": vessel.get("type")}
