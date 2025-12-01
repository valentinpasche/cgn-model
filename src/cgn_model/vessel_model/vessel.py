# cgn_model/vessel_model/vessel.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import copy
import yaml
import numpy as np
from numpy.typing import NDArray

from cgn_model.energy_solver import SolverDAG
from cgn_model.energy_solver.types import Mode

from cgn_model.vessel_model.config import (
    VesselType,
    VesselCfg,
    ProfileCfg,
    AdapterCfg,
    InputBindCfg,
)
from cgn_model.vessel_model.adapters import AdapterABC, build_adapter_from_cfg

type FArray = NDArray[np.floating]
type SolverMode = Mode


__all__ = ["Vessel"]

# ---------------- Types & runtime entities ----------------

@dataclass
class Profile:
    """
    Profil brut tel que déclaré côté YAML (après résolution 'data'/'file').
    - unit : unité telle que fournie (ex. 'kn', 'W', 'm/s', 'kW'...)
    - data : vecteur 1D (float64)
    """
    id: str
    unit: str
    data: FArray

@dataclass
class InputBind:
    """
    Liaison 'input du solver' -> source (profil ou adapter).
    - id   : identifiant de l'input (côté solver)
    - bus  : bus cible (côté solver)
    - source : id d'un Profile ou d'un Adapter (résolu dans Vessel)
    """
    id: str
    bus: str
    source: str

type Profiles = dict[str, Profile]
type Signals = dict[str, tuple[FArray, str]]  # id -> (array, unit)
type Adapters = dict[str, AdapterABC]

__all__ = ["Vessel"]


# ========================== Vessel ==========================

@dataclass
class Vessel:
    """
    Orchestrateur 'métier' :
      - lit les métadonnées du bateau (name, vessel_type),
      - prépare le solver DAG (énergie),
      - charge profiles/adapters/bindings et matérialise les signaux utilisables par le solver.
    """
    name: str
    vessel_type: VesselType
    solver: SolverDAG

    # runtime (facultatif, utile pour itérer/inspecter)
    profiles: Profiles | None = None
    adapters: Adapters | None = None
    input_binds: list[InputBind] | None = None
    signals: Signals | None = None  # profils bruts + adapters matérialisés

    # -------- Construction principale --------
    @classmethod
    def from_yaml(cls, cfg: str | dict[str, Any]) -> "Vessel":
        """
        Construit le Vessel + le SolverDAG.
        Ne lance pas la simulation; prépare les structures.
        """
        # 1) Métadonnées (name, vessel_type)
        meta = cls._parse_cfg(cfg)
        meta_model = cls._validate_cfg(meta)

        # 2) Solver (utilise le YAML complet ; son _parse_cfg interne filtrera)
        solver = SolverDAG.from_yaml(cfg)

        # 3) Sections 'métier' (profiles/adapters/inputs) → runtime objects
        raw = cls._extract_sections(cfg)
        profiles = cls._build_profiles(raw["profiles"])
        adapters = cls._build_adapters(raw["adapters"])
        input_binds = cls._build_input_binds(raw["inputs"])

        # 4) Matérialiser tous les signaux (profiles bruts + adapters)
        signals = cls._materialize_signals(profiles, adapters)

        return cls(
            name=meta_model.name,
            vessel_type=meta_model.vessel_type,
            solver=solver,
            profiles=profiles,
            adapters=adapters,
            input_binds=input_binds,
            signals=signals,
        )

    # -------- Parse / Validate (métadonnées) --------
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

        # --- Accepter 'vessel_type' ou 'type'
        vt_raw = vessel.get("vessel_type", None)
        t_raw  = vessel.get("type", None)

        def _norm(s): return (s or "").strip().lower()
        if vt_raw is not None and t_raw is not None and _norm(vt_raw) != _norm(t_raw):
            raise ValueError(
                f"Conflit entre 'vessel_type'={vt_raw!r} et 'type'={t_raw!r}. "
                "Ne fournissez qu'une seule des deux clés, avec la même valeur."
            )

        raw = vt_raw if vt_raw is not None else t_raw
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            vessel_type = "undefined"
        else:
            s = raw.strip().lower()
            synonyms = {
                "de": "DE", "diesel": "DE", "diesel_engine": "DE",
                "steam": "steam", "vapeur": "steam",
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

        return {"name": vessel.get("name"), "vessel_type": vessel_type}

    @staticmethod
    def _validate_cfg(parsed: dict[str, Any]) -> VesselCfg:
        """Valide les métadonnées via Pydantic."""
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

    # -------- Extraction des sections vessel --------
    @staticmethod
    def _extract_sections(cfg: str | dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Récupère (sans effet de bord) profiles/adapters/inputs tels que fournis dans le YAML."""
        source = yaml.safe_load(cfg) if isinstance(cfg, str) else cfg
        if not isinstance(source, dict) or source is None:
            raise ValueError("La configuration YAML est vide ou n'est pas un mapping.")
        pick = copy.deepcopy  # pas d'effet de bord

        def _ensure_list(value, section: str) -> list[dict[str, Any]]:
            if value is None:
                return []
            if isinstance(value, list):
                if not all(isinstance(x, dict) for x in value):
                    raise TypeError(f"Section '{section}' doit contenir des mappings (dict).")
                return value
            if isinstance(value, dict):
                return [value]
            raise TypeError(f"Section '{section}' doit être liste ou mapping; reçu {type(value).__name__}.")

        return {
            "profiles":   _ensure_list(pick(source.get("profiles")),   "profiles"),
            "adapters":   _ensure_list(pick(source.get("adapters")),   "adapters"),
            "inputs":     _ensure_list(pick(source.get("inputs")),     "inputs"),  # bindings côté vessel
        }

    # -------- Builders runtime --------
    @staticmethod
    def _build_profiles(cfg_profiles: list[dict[str, Any]]) -> Profiles:
        profiles: Profiles = {}
        for i, raw in enumerate(cfg_profiles):
            p = ProfileCfg.model_validate(raw)
            if p.data is None:
                # support 'file' non implémenté ici
                raise ValueError(f"Profile {p.id!r}: 'data' manquant (support 'file' non implémenté).")
            arr = np.asarray(p.data, dtype=np.float64)
            profiles[p.id] = Profile(id=p.id, unit=p.unit, data=arr)
        return profiles

    @staticmethod
    def _build_adapters(cfg_adapters: list[dict[str, Any]]) -> Adapters:
        adapters: Adapters = {}
        for raw in cfg_adapters:
            a = AdapterCfg.model_validate(raw)
            adapters[a.id] = build_adapter_from_cfg(a)
        return adapters

    @staticmethod
    def _build_input_binds(cfg_inputs: list[dict[str, Any]]) -> list[InputBind]:
        binds: list[InputBind] = []
        for raw in cfg_inputs:
            b = InputBindCfg.model_validate(raw)
            binds.append(InputBind(id=b.id, bus=b.bus, source=b.source))
        return binds

    # -------- Matérialisation des signaux --------
    @staticmethod
    def _materialize_signals(
        profiles: dict[str, Profile],
        adapters: dict[str, AdapterABC],
    ) -> Signals:
        """
        Produit un dict id -> (array, unit) contenant :
          - tous les profiles bruts (tels quels),
          - tous les adapters évalués (ordre topologique résolu).
        """
        signals: Signals = {pid: (p.data, p.unit) for pid, p in profiles.items()}

        remaining = dict(adapters)
        guard = 0
        while remaining:
            progressed = []
            for aid, adapter in remaining.items():
                src = adapter.source
                if src in signals:
                    series, unit = signals[src]
                    out_series, out_unit = adapter.apply(series, unit)
                    signals[aid] = (out_series, out_unit)
                    progressed.append(aid)
            for aid in progressed:
                remaining.pop(aid)
            guard += 1
            if guard > 1000:
                raise RuntimeError("Cycle ou source manquante dans les adapters.")
        return signals

    # -------- Préparation des inputs pour le solver --------
    def build_solver_inputs(self) -> dict[str, tuple[str, FArray]]:
        """
        Retourne un mapping prêt pour le solver :
            input_id -> (bus_id, profile_W)

        Pré-conditions :
          - self.signals est construit (via from_yaml)
          - chaque binding.source doit mener à un signal en 'W'
            (les adapters doivent donc produire de la puissance)

        NB: injection effective dans le solver à faire côté appelant
            (ex: via ta fonction prepare_state/run_vector).
        """
        if self.signals is None or self.input_binds is None:
            raise RuntimeError("Vessel non initialisé (signals/input_binds manquants).")

        result: dict[str, tuple[str, FArray]] = {}
        for bind in self.input_binds:
            try:
                arr, unit = self.signals[bind.source]
            except KeyError:
                raise KeyError(f"Source inconnue pour l'input {bind.id!r}: {bind.source!r}")

            if unit != "W":
                raise ValueError(
                    f"Le binding {bind.id!r} fournit une unité {unit!r} ≠ 'W'. "
                    "Assure-toi que l'adapter produit des W (ex. kind='poly_speed_to_power')."
                )
            result[bind.id] = (bind.bus, np.asarray(arr, dtype=np.float64))
        return result


# --------------------------- Demo ---------------------------
if __name__ == "__main__":
    # Petit test manuel (optionnel)
    cfg_txt = """
vessel:
  name: "Vevey"
  vessel_type: "DE"                   # la clé "type" est aussi acceptée

profiles:
  - id: "speed"
    unit: "kn"
    data: [10, 12, 15, 12, 8]         # ou file: "speed.csv"

  - id: "hotel_load"
    unit: "W"
    data: [8000, 8200, 7500, 7600, 7800]

adapters:
  - id: "shaft_power_from_speed"
    kind: "poly_speed_to_power"
    source: "speed"
    unit_in: "m/s"                    # l’adapter attend m/s
    unit_out: "W"                     # et produit des W
    params:
      coeffs: [0.0, 100.0, 0.0, 5.0]  # exemple ([a0, a1, a2] -> P = a0 + a1*v + a2*v^2)

inputs:
  - id: "shaft_demand"
    bus: "Mechanical:shaft"
    source: "shaft_power_from_speed"  # via l’adapter (clé ignorée par le solver, utilisé par Vessel)

  - id: "navops"
    bus: "Electrical:main"
    source: "hotel_load"              # direct: déjà en W

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
    params: { eta: 0.38 }

  - id: "motor"
    from_bus: "Electrical:main"
    to_bus:   "Mechanical:shaft"
    kind: "constant_eta"
    params: { eta: 0.9 }
"""
    
    cfg = yaml.safe_load(cfg_txt)
    vessel = Vessel.from_yaml(cfg)
    mapping = vessel.build_solver_inputs()
    for k, (bus, arr) in mapping.items():
        print(k, "->", bus, "| len:", len(arr), "| first:", float(arr[0]))

    
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
        