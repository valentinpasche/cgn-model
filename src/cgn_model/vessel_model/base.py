# cgn_model/vessel_model/base.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal
from pydantic import BaseModel, StrictStr, ConfigDict, model_validator
import copy, yaml

from numpy.typing import NDArray
import numpy as np

from cgn_model.energy_solver import SolverDAG
from cgn_model.energy_solver.types import Mode

type FArray = NDArray[np.floating]
type SolverMode = Mode
type VesselType = Literal["DE", "steam", "undefined"]

__all__ = ["Vessel"]

class VesselCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: StrictStr
    vessel_type: VesselType

    @model_validator(mode="after")
    def check_fields(self):
        return self

@dataclass
class Vessel:
    name: str
    vessel_type: VesselType
    solver: SolverDAG

    @classmethod
    def from_yaml(cls, cfg: str | dict[str, Any]) -> "Vessel":
        parsed = cls._parse_cfg(cfg)          # forme normalisée
        cfg_model = cls._validate_cfg(parsed) # Pydantic
        solver = SolverDAG.from_yaml(cfg)
        return cls(name=cfg_model.name, vessel_type=cfg_model.vessel_type, solver=solver)

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
        
        # --- Tratement "type de propulsion" ---
        
        # 1) lire brut
        t_raw = vessel.get("type", None)
        
        # 2) cas "absent" ou vide -> undefined
        if t_raw is None or (isinstance(t_raw, str) and t_raw.strip() == ""):
            vessel["type"] = "undefined"
        else:
            # 3) normalisation + synonymes
            t_norm = t_raw.strip().lower()
            synonyms = {
                # diesel electric
                "de": "DE",
                "diesel": "DE",
                "diesel_engine": "DE",
                "diesel_electric": "DE",
        
                # vapeur / steam
                "steam": "steam",
                "vapeur": "steam",
        
                # on tolère aussi "undefined"
                "undefined": "undefined",
            }
            mapped = synonyms.get(t_norm)
            if mapped is None:
                # 4) valeur inconnue -> erreur lisible
                raise ValueError(
                    f"Type de propulsion invalide: {t_raw!r}. "
                    "Valeurs attendues: 'DE' (synonymes: de, diesel) ou 'steam' (synonymes: steam, vapeur). "
                    "Laissez vide pour 'undefined'."
                )
            vessel["type"] = mapped
        
        return {"name": vessel.get("name"), "vessel_type": vessel.get("type")}
    
    @staticmethod
    def _validate_cfg(parsed: dict[str, Any]) -> VesselCfg:
        """
        Valide et type avec Pydantic. Retourne une instance Cfg.
        Lève ValueError avec un message lisible en cas d'erreur.
        """
        from pydantic import ValidationError
        try:
            return VesselCfg.model_validate(parsed)
        except ValidationError as e:
            lines = []
            for err in e.errors():
                loc = " -> ".join(str(p) for p in err.get("loc", ()))
                msg = err.get("msg", "invalid")
                lines.append(f"- {loc}: {msg}")
            pretty = "\n".join(lines)
            raise ValueError(f"YAML invalide:\n{pretty}") from e




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
        kind: "constant_eta"
        params:
          eta:  0.9
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
        print("\nOK : Les 2 solveurs sont identiques !\n")
    else:
        print("\nATTENTION : Les 2 solveurs sont différents !\n")
        