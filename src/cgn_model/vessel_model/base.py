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



# Test config - Creation Vessel avec SolverDAG
if __name__ == "__main__":
    
    # Config
    cfg_txt = """
    vessel:
      name: "Vevey"
      type: "DE"
      
    profil_vitesse:
        coefs:
          [0.2, 0.3, -2, ..]
    
    solver:
      mode: "inverse"
    
    buses:
      - {id: "Mechanical:shaft", carrier: "Mechanical"}
      - {id: "Electrical:main",  carrier: "Electrical"}
      - {id: "Chemical:fuel",    carrier: "Chemical"}
    
    inputs:
      - {id: "shaft_demand", bus: "Mechanical:shaft"}
      - {id: "navops",       bus: "Electrical:main"}
    
    converters:
      - id: "genset"
        from_bus: "Chemical:fuel"
        to_bus:   "Electrical:main"
        kind: "constant_eta"
        params:
          eta:  0.38 
      - id: "motor"
        from_bus: "Electrical:main"
        to_bus:   "Mechanical:shaft"
        eta:  0.9    # Fallback sur "constant_eta" si "kind" non renseigé et "eta" présent au top-level
    """
    
    cfg = yaml.safe_load(cfg_txt)
    solver = SolverDAG.from_yaml(cfg)
    vessel = Vessel.from_yaml(cfg)
    
    def validation_init_solver(vessel, solver):
        dct_vessel_solver = vars(vessel.solver)
        dct_solver = vars(solver)
        # Les ID des Graphs ne sont pas identiques
        del dct_vessel_solver["dag"]
        del dct_solver["dag"]
        return dct_vessel_solver == dct_solver
    
    if validation_init_solver(vessel, solver):
        print("OK : Les 2 solveurs sont identiques !")
    else:
        print("ATTENTION : Les 2 solveurs sont différents !")
        