# cgn_model/vessel_model/vessel.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import copy, yaml

from numpy.typing import NDArray
import numpy as np

from cgn_model.energy_solver import SolverDAG
from cgn_model.energy_solver.types import Mode

from cgn_model.vessel_model.config import (
    VesselType,
    VesselCfg,
)

type FArray = NDArray[np.floating]
type SolverMode = Mode


__all__ = ["Vessel"]



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
        return cls(
            name=cfg_model.name,
            vessel_type=cfg_model.vessel_type,
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
    
        # Fallback nom
        vessel.setdefault("name", "unknown")
    
        # --- Traitement du type de propulsion: accepter 'vessel_type' ou 'type'
        vt_raw = vessel.get("vessel_type", None)
        t_raw  = vessel.get("type", None)
    
        # Conflit explicite si les deux sont fournis et diffèrent (après strip/lower)
        def _norm(s):
            return (s or "").strip().lower()
    
        if vt_raw is not None and t_raw is not None and _norm(vt_raw) != _norm(t_raw):
            raise ValueError(
                f"Conflit entre 'vessel_type'={vt_raw!r} et 'type'={t_raw!r}. "
                "Ne fournissez qu'une seule des deux clés, avec la même valeur."
            )
    
        # Choix de la source (priorité à 'vessel_type')
        raw = vt_raw if vt_raw is not None else t_raw
    
        # Vide/absent -> undefined
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            vessel_type = "undefined"
        else:
            s = raw.strip().lower()
            synonyms = {
                # Diesel
                "de": "DE",
                "diesel": "DE",
                "diesel_engine": "DE",
                # Vapeur
                "steam": "steam",
                "vapeur": "steam",
                # On tolère explicitement 'undefined'
                "undefined": "undefined",
            }
            mapped = synonyms.get(s)
            if mapped is None:
                raise ValueError(
                    f"Type de propulsion invalide: {raw!r}. "
                    "Valeurs attendues: 'DE' (synonymes: de, diesel) ou 'steam' (synonymes: steam, vapeur). "
                    "Laissez vide pour 'undefined'."
                )
            vessel_type = mapped
    
        # Sortie normalisée pour Pydantic
        return {
            "name": vessel.get("name"),
            "vessel_type": vessel_type,
        }
    
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
      vessel_type: "DE"
    
    profiles:
      - id: "speed"
        unit: "kn"
        data: [10, 12, 15, 12, 8]    # ou file: "speed.csv"
    
      - id: "hotel_load"
        unit: "W"
        data: [8000, 8200, 7500, 7600, 7800]
    
    adapters:
      - id: "shaft_power_from_speed"
        kind: "poly"
        source: "speed"
        unit_in: "m/s"            # l’adapter attend m/s
        unit_out: "W"             # et produit des W
        params:
          coeffs: [a0, a1, a2, a3]  # P = a0 + a1*v + a2*v^2 + a3*v^3
    
    inputs:
      - id: "shaft_demand"
        bus: "Mechanical:shaft"
        source: "shaft_power_from_speed"   # via l’adapter
    
      - id: "navops"
        bus: "Electrical:main"
        source: "hotel_load"      # direct: déjà en W
    
    solver:
      mode: "inverse"
    
    buses:
      - { id: "Mechanical:shaft", carrier: "Mechanical" }   # unit implicite "W"
      - { id: "Electrical:main",  carrier: "Electrical" }
      - { id: "Chemical:fuel",    carrier: "Chemical" }
    
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
    
    vessel = Vessel.from_yaml(cfg)
    
    # # === Validation de la config en 2 paties, Vessel -> Solveur ===
    
    # def validation_init_solver(vessel, solver):
    #     dct_vessel_solver = vars(vessel.solver)
    #     dct_solver = vars(solver)
    #     # Les ID des Graphs ne sont pas identiques
    #     del dct_vessel_solver["dag"]
    #     del dct_solver["dag"]
    #     return dct_vessel_solver == dct_solver
    
    # solver = SolverDAG.from_yaml(cfg)
    
    # if validation_init_solver(vessel, solver):
    #     print("\nOK : Les 2 solveurs sont identiques !\n")
    # else:
    #     print("\nATTENTION : Les 2 solveurs sont différents !\n")
        