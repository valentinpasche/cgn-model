# cgn_model/vessel_model/vessel.py

"""
Orchestrateur vessel : chargement des profils, adapters et integration solver.

Ce module fait la transition entre la configuration metier du bateau et le
solveur energetique generique. Le pipeline principal est :

    YAML -> Vessel -> profiles -> adapters -> inputs signes
         -> SolverDAG.prepare_state/run_vector -> storages/results

Le `Vessel` ne resout pas directement les flux d'energie. Il prepare les signaux,
applique les conventions metier (unites, signes, sources) et transmet au
`SolverDAG` uniquement des profils de puissance signes en W.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import copy
import yaml
import numpy as np
from numpy.typing import NDArray
import warnings

from cgn_model.energy_solver import SolverDAG
from cgn_model.energy_solver.types import Mode

from cgn_model.vessel_model.config import (
    VesselType,
    VesselCfg,
    AdapterCfg,
    InputBindCfg,
    ProfileCfg,
    VesselSectionsCfg,
    StorageCfg,
)
from cgn_model.vessel_model.profiles import (
    _load_csv_column,
    _build_nav_speed,
    _pick_master_id,
    Profile,
)
from cgn_model.vessel_model.signals import (
    _apply_sign_policy,
    _warn_inconsistent_sign,
    InputBind,
    Signals,
)
from cgn_model.vessel_model.adapters import AdapterABC, build_adapter_from_cfg
from cgn_model.vessel_model.results_utils import (
    results_col_name,
    unit_from_storage_col,
    strip_storage_unit_suffix,
)
from cgn_model.vessel_model.storage import StorageResult

type FArray = NDArray[np.floating]
type SolverMode = Mode

__all__ = ["Vessel"]

# ========================== Vessel ==========================

@dataclass
class Vessel:
    """
    Orchestrateur metier pour preparer le solver et les signaux.

    `Vessel` est la couche de traduction entre le YAML complet et le `SolverDAG`.
    Il garde les notions metier (profils, navigation, adapters, bindings
    d'inputs, stockages) et prepare pour le solver une interface plus simple :
    des bus, des convertisseurs et des profils de puissance signes.

    Pipeline principal
    ------------------
    1. lire/valider les metadonnees du bateau ;
    2. construire le `SolverDAG` depuis les sections solver du YAML ;
    3. construire les profils bruts (`profiles`) ;
    4. construire les transformations (`adapters`) ;
    5. materialiser tous les signaux disponibles ;
    6. appliquer les bindings d'inputs et les conventions de signe ;
    7. preparer le solver avec `prepare_state` ;
    8. post-traiter les stockages et exporter les resultats si besoin.

    Cette classe est volontairement un orchestrateur : elle coordonne plusieurs
    objets, mais laisse le calcul de propagation energetique au `SolverDAG`.

    Attributes
    ----------
    name : str
        Nom du vessel.
    vessel_type : VesselType
        Type de propulsion.
    solver : SolverDAG
        Solveur DAG associe.
    dt : float
        Pas de temps global [s].
    """
    name: str
    vessel_type: VesselType
    solver: SolverDAG
    dt: float

    # runtime (facultatif, utile pour itérer/inspecter)
    profiles: dict[str, Profile] | None = None
    adapters: dict[str, AdapterABC] | None = None
    input_binds: list[InputBind] | None = None
    signals: dict[str, tuple[FArray, str]] | None = None  # profils bruts + adapters matérialisés
    storages_cfg: list[StorageCfg] | None = None
    storages: dict[str, StorageResult] | None = None
    
    @property
    def t(self):
        """
        Vecteur temps [s] si le solver est initialise.
        """
        for b in self.solver.buses.values():
            if b.net_w is not None:
                N = len(b.net_w)
                return np.arange(N, dtype=float) * float(self.dt)
        return None
    
    # -------- Construction principale --------
    @classmethod
    def from_yaml(cls, cfg: str | dict[str, Any], *, check_ids: bool = True) -> "Vessel":
        """
        Construit un Vessel et le SolverDAG a partir d'un YAML.

        Parameters
        ----------
        cfg : str | dict
            YAML texte ou dictionnaire deja charge.
        check_ids : bool, optional
            Si True, verifie l'absence de collisions d'IDs entre sections vessel et solver
            (les IDs d'inputs sont autorises a se superposer).

        Returns
        -------
        Vessel
            Instance prete a construire les inputs.

        Notes
        -----
        Le YAML contient deux niveaux de responsabilite :
        - les sections metier (`profiles`, `adapters`, `storages`, etc.) sont
          conservees et interpretees par `Vessel` ;
        - les sections energetiques (`solver`, `buses`, `converters`, `inputs`)
          sont filtrees et preparees par `SolverDAG`.

        Cette separation permet de garder un solveur generique, tout en laissant
        au `Vessel` la responsabilite de traduire le scenario metier en signaux.
        """
        # 1) Metadonnees vessel (name, vessel_type).
        meta = cls._parse_cfg(cfg)
        meta_model = cls._validate_cfg(meta)

        # 2) Structure solver: bus, convertisseurs, inputs et plan DAG.
        #    Le SolverDAG filtre lui-meme les sections qui le concernent.
        solver = SolverDAG.from_yaml(cfg)

        # 3) Sections metier: profils, adapters, bindings d'inputs et stockages.
        raw = cls._extract_sections(cfg)
        sections = VesselSectionsCfg.model_validate(raw)   # declenche cross_checks()
        if check_ids:
            cls._check_id_collisions(sections=sections, solver=solver)

        # 4) Objets runtime cote Vessel.
        dt = float(sections.simulation.dt)
        profiles    = cls._build_profiles(sections.profiles, dt)
        adapters    = cls._build_adapters(sections.adapters)
        input_binds = cls._build_input_binds(sections.inputs)
        # Garde la config des storages
        storages_raw = getattr(sections, "storages", None)
        storages_cfg = list(storages_raw) if storages_raw is not None else []
        storages=None

        # 5) Materialisation des signaux: profiles bruts + sorties d'adapters.
        signals = cls._materialize_signals(profiles, adapters)

        return cls(
            name=meta_model.name,
            vessel_type=meta_model.vessel_type,
            solver=solver,
            dt=dt,
            profiles=profiles,
            adapters=adapters,
            input_binds=input_binds,
            signals=signals,
            storages_cfg=storages_cfg,
            storages=storages,
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
        """
        Valide les metadonnees via Pydantic.
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

    # -------- Extraction des sections vessel --------
    @staticmethod
    def _extract_sections(cfg: str | dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """
        Extrait les sections vessel sans effet de bord.

        Returns
        -------
        dict
            Dictionnaire avec simulation, profiles, adapters, inputs, storages.
        """
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
            "simulation": pick(source.get("simulation", {})),
            "profiles":   _ensure_list(pick(source.get("profiles")), "profiles"),
            "adapters":   _ensure_list(pick(source.get("adapters")), "adapters"),
            "inputs":     _ensure_list(pick(source.get("inputs")),   "inputs"),  # bindings côté vessel
            "storages":   _ensure_list(pick(source.get("storages")), "storages"),
        }

    @staticmethod
    def _check_id_collisions(sections: VesselSectionsCfg, solver: SolverDAG) -> None:
        """
        Verifie l'absence de collisions d'IDs entre les sections vessel et le solver.

        Notes
        -----
        Les IDs des inputs peuvent se superposer entre vessel et solver.
        """
        vessel_ids = {
            "profiles": {p.id for p in sections.profiles},
            "adapters": {a.id for a in sections.adapters},
            "inputs": {i.id for i in sections.inputs},
            "storages": {s.id for s in sections.storages},
        }
        solver_ids = {
            "buses": set(solver.buses.keys()),
            "converters": set(solver.converters.keys()),
            "inputs": set(solver.inputs.keys()),
        }

        collisions: list[str] = []
        for v_name, v_set in vessel_ids.items():
            for s_name, s_set in solver_ids.items():
                if v_name == "inputs" and s_name == "inputs":
                    continue
                overlap = sorted(v_set & s_set)
                if overlap:
                    collisions.append(f"{v_name} vs {s_name}: {overlap}")

        if collisions:
            details = "; ".join(collisions)
            raise ValueError(
                "IDs dupliques entre sections vessel et solver: "
                f"{details}. Les IDs d'inputs peuvent se superposer."
            )
# -------- Builders runtime --------    
    @staticmethod
    def _build_profiles(cfg_profiles: list[ProfileCfg], dt: float) -> dict[str, Profile]:
        """
        Construit les profils runtime et harmonise leur longueur temporelle.

        Parameters
        ----------
        cfg_profiles : list[ProfileCfg]
            Profils declares dans le YAML (constant, series, file ou nav_speed).
        dt : float
            Pas de temps global [s], transmis aux profils de navigation.

        Returns
        -------
        dict[str, Profile]
            Profils 1D prets a alimenter les adapters ou les inputs.

        Notes
        -----
        Le profil maitre fixe la longueur N. Les profils constants sont etendus
        a cette longueur, tandis que les series/fichiers doivent deja avoir la
        meme longueur.
        """
        profiles: dict[str, Profile] = {}
    
        # Le maitre fixe l'horizon temporel N sans construire plusieurs fois
        # un profil de navigation potentiellement couteux.
        master_id = _pick_master_id(cfg_profiles)
        master_obj = next(p for p in cfg_profiles if p.id == master_id)
    
        if master_obj.kind == "nav_speed":
            data = _build_nav_speed(
                source=master_obj.source,
                select=master_obj.select,
                params=master_obj.params,
                dt=dt,
            )
        elif master_obj.kind == "series":
            data = np.asarray(master_obj.data, dtype=np.float64)
        elif master_obj.kind == "file":
            data = _load_csv_column(
                file=master_obj.file,
                column=master_obj.column,
                sep=master_obj.sep,
                decimal=master_obj.decimal,
                encoding=master_obj.encoding,
            )
        else:
            # on a déjà interdit 'constant' comme maître
            raise NotImplementedError(f"Profil maître de kind {master_obj.kind!r} non géré")
    
        N = int(data.shape[0])
        profiles[master_obj.id] = Profile(id=master_obj.id, unit=master_obj.unit, data=data)
    
        # Les profils non maitres doivent partager l'horizon N. Une constante
        # scalaire est diffusee sur N; une serie explicite doit deja avoir N
        # points pour eviter une interpolation implicite.
        for p in cfg_profiles:
            if p.id == master_id:
                continue
    
            if p.kind == "constant":
                vals = p.value if isinstance(p.value, list) else [p.value]
                if len(vals) == 1:
                    arr = np.full(N, float(vals[0]), dtype=np.float64)
                elif len(vals) == N:
                    arr = np.asarray(vals, dtype=np.float64)
                else:
                    raise ValueError(f"Profil constant {p.id!r}: longueur {len(vals)} incompatible avec N={N}.")
                profiles[p.id] = Profile(id=p.id, unit=p.unit, data=arr)
    
            elif p.kind == "series":
                arr = np.asarray(p.data, dtype=np.float64)
                if arr.shape[0] != N:
                    raise ValueError(f"Profil {p.id!r}: len={len(arr)} != N={N}.")
                profiles[p.id] = Profile(id=p.id, unit=p.unit, data=arr)
    
            elif p.kind == "file":
                arr = _load_csv_column(
                    file=p.file,
                    column=p.column,
                    sep=p.sep,
                    decimal=p.decimal,
                    encoding=p.encoding,
                )
                if arr.shape[0] != N:
                    raise ValueError(f"Profil fichier {p.id!r}: len={len(arr)} != N={N}.")
                profiles[p.id] = Profile(id=p.id, unit=p.unit, data=arr)
    
            elif p.kind == "nav_speed":
                arr = _build_nav_speed(source=p.source, select=p.select, params=p.params, dt=dt)
                if arr.shape[0] != N:
                    raise ValueError(f"Profil nav_speed {p.id!r}: len={len(arr)} != N={N}.")
                profiles[p.id] = Profile(id=p.id, unit=p.unit, data=arr)
    
            else:
                raise NotImplementedError(f"Profile kind non supporté: {p.kind!r}")
    
        return profiles

    @staticmethod
    def _build_adapters(cfg_adapters: list[AdapterCfg]) -> dict[str, AdapterABC]:
        """
        Instancie les adapters runtime depuis les configurations validees.

        Parameters
        ----------
        cfg_adapters : list[AdapterCfg]
            Configurations d'adapters issues du YAML.

        Returns
        -------
        dict[str, AdapterABC]
            Adapters indexes par ID.
        """
        adapters = {a.id: build_adapter_from_cfg(a) for a in cfg_adapters}
        return adapters

    @staticmethod
    def _build_input_binds(cfg_inputs: list[InputBindCfg]) -> list[InputBind]:
        """
        Convertit les bindings YAML en dataclasses runtime.

        Parameters
        ----------
        cfg_inputs : list[InputBindCfg]
            Liaisons input solver -> signal source.

        Returns
        -------
        list[InputBind]
            Bindings conservant bus, source, convention de signe et scale.
        """
        binds: list[InputBind] = []
        for b in cfg_inputs:
            # Construire les kwargs sans 'scale' si absent -> la dataclass appliquera 1.0
            kwargs: dict[str, object] = dict(id=b.id, bus=b.bus, source=b.source, sign=b.sign)
            if b.scale is not None:
                kwargs["scale"] = float(b.scale)  # on ne met l’argument que s’il existe
            binds.append(InputBind(**kwargs))
        return binds

    # -------- Matérialisation des signaux --------
    @staticmethod
    def _materialize_signals(
        profiles: dict[str, Profile],
        adapters: dict[str, AdapterABC],
    ) -> Signals:
        """
        Materilise tous les signaux (profiles + adapters).

        Parameters
        ----------
        profiles : dict[str, Profile]
            Profils bruts.
        adapters : dict[str, AdapterABC]
            Adapters construits.

        Returns
        -------
        dict[str, tuple[numpy.ndarray, str]]
            Mapping id -> (array, unit).
        """
        signals: Signals = {pid: (p.data, p.unit) for pid, p in profiles.items()}
    
        remaining = dict(adapters)
        guard = 0
        while remaining:
            progressed = []
            for aid, adapter in remaining.items():
                req = adapter.required_sources()
                if all(sid in signals for sid in req):
                    # Les adapters sont materialises uniquement quand toutes
                    # leurs sources sont deja disponibles; cela donne un ordre
                    # topologique sans dupliquer la logique de validation.
                    inputs = {sid: signals[sid] for sid in req}
                    out_series, out_unit = adapter.apply_multi(inputs)
                    signals[aid] = (out_series, out_unit)
                    progressed.append(aid)
            for aid in progressed:
                remaining.pop(aid)
            guard += 1
            if guard > 1000:
                missing = {aid: adapter.required_sources() for aid, adapter in remaining.items()}
                raise RuntimeError(f"Cycle ou sources manquantes dans les adapters: {missing}")
        return signals

    # -------- Pipeline: signaux Vessel -> profils signes du SolverDAG --------
    def build_solver_inputs(
        self,
        *,
        profiles_only: bool = False,
        verbose: bool = False,
        auto_convert: bool = False,
    ) -> dict[str, FArray] | dict[str, tuple[str, FArray]]:
        """
        Prepare les profils d'inputs attendus par `prepare_state`.

        Cette methode est le point de passage entre les signaux metier du
        `Vessel` et les inputs numeriques du `SolverDAG`. Elle recupere la
        source declaree par chaque `InputBind`, convertit eventuellement le
        signal en W, applique `scale`, puis applique la convention de signe.

        Parameters
        ----------
        profiles_only : bool, optional
            Si True, retourne uniquement ``{input_id: array}``. Sinon retourne
            ``{input_id: (bus_id, array)}`` pour permettre le controle du bus.
        verbose : bool, optional
            Affiche un resume des profils construits.
        auto_convert : bool, optional
            Convertit automatiquement vers W lorsque la source n'est pas deja
            dans l'unite du solver.

        Returns
        -------
        dict[str, FArray] | dict[str, tuple[str, FArray]]
            Profils 1D signes en W, indexes par ID d'input solver.

        Notes
        -----
        Convention solver :
        - valeur positive : injection sur le bus ;
        - valeur negative : demande/retrait sur le bus.

        Convention YAML :
        - ``sign: consume`` force le profil en negatif ;
        - ``sign: inject`` force le profil en positif ;
        - ``sign: as_is`` conserve le signe de la source.
        """
        if self.signals is None or self.input_binds is None:
            raise RuntimeError("Vessel non initialisé (signals/input_binds manquants).")
    
        from cgn_model.vessel_model.adapters import convert_unit  # si pas déjà importé
    
        # bus cible attendu par le solver pour chaque input
        solver_bus_by_input = {inp_id: inp.bus for inp_id, inp in self.solver.inputs.items()}
    
        full: dict[str, tuple[str, np.ndarray]] = {}
        for bind in self.input_binds:
            try:
                arr, unit = self.signals[bind.source]
            except KeyError:
                raise KeyError(f"Source inconnue pour l'input {bind.id!r}: {bind.source!r}")
    
            # 1) s’assurer d’être en W
            if unit != "W":
                if not auto_convert:
                    raise ValueError(
                        f"Le binding {bind.id!r} fournit une unité {unit!r} ≠ 'W'. "
                        "Assure-toi que l'adapter produit des W (p.ex. kind='speed_to_power_poly'), "
                        "ou passe auto_convert=True pour convertir ici."
                    )
                try:
                    arr, unit = convert_unit(arr, unit_in=unit, unit_out="W", quantity="power")
                except Exception as e:
                    raise ValueError(f"Conversion en 'W' impossible pour {bind.id!r} depuis {unit!r}: {e}") from e
    
            # 2) vérifier le bus attendu (cohérence YAML vs solver)
            bus_expected = solver_bus_by_input.get(bind.id)
            if bus_expected is None:
                raise KeyError(f"L'input {bind.id!r} n'existe pas dans le solver.")
            if bind.bus != bus_expected:
                raise ValueError(
                    f"Bus mismatch pour l'input {bind.id!r}: YAML={bind.bus!r} vs Solver={bus_expected!r}"
                )
    
            # 3) normalisations finales
            arr_w = np.asarray(arr, dtype=np.float64)
            if arr_w.ndim != 1:
                raise ValueError(f"Profil {bind.id!r}: attendu 1D, obtenu shape={arr_w.shape}")
            if not np.isfinite(arr_w).all():
                raise ValueError(f"Profil {bind.id!r}: valeurs non finies (NaN/Inf) détectées.")
    
            # La convention de signe est appliquee au dernier moment avant le
            # solver, pour garder les profils/adapters en grandeurs physiques
            # positives quand c'est leur representation naturelle.
            arr_signed = _apply_sign_policy(arr_w, bind.sign, bind.scale)
            
            # Controle informatif: apres application de la convention, un
            # profil consume devrait etre <= 0 et un profil inject >= 0.
            if bind.sign in ("consume", "inject"):
                total, wrong, frac = _warn_inconsistent_sign(arr_signed, bind.sign)
                if verbose:
                    print(
                        f"[inputs] {bind.id} sign={bind.sign} | total:{total} "
                        f"| wrong:{wrong} ({frac*100:.3f}%) "
                        f"| min:{arr_signed.min():.3g} | max:{arr_signed.max():.3g}"
                    )
    
            full[bind.id] = (bind.bus, arr_signed)
    
            if verbose:
                print(f"[inputs] {bind.id} -> {bind.bus}",
                      "| len:", len(arr_signed),
                      "| first:", round(float(arr_signed[0]),2),
                      "| max:", round(max(arr_signed),2)
                )
    
        return {k: v[1] for k, v in full.items()} if profiles_only else full
    
    # -------- Pipeline: application effective des inputs au SolverDAG --------
    def apply_inputs_to_solver(
        self,
        *,
        strict: bool = True,
        verbose: bool = False,
        auto_convert: bool = False,
        eta_autowire: bool = False,
        clip_eta_profile: bool = True,
    ) -> int:
        """
        Applique les inputs au solver via prepare_state.

        Cette methode initialise l'etat numerique du `SolverDAG` a partir des
        profils signes construits par `build_solver_inputs()`. Apres cet appel,
        les bus possedent un `net_w` initial et les inputs du solver portent
        leurs profils.

        Parameters
        ----------
        strict : bool, optional
            Verifie que toutes les longueurs sont identiques.
        verbose : bool, optional
            Active les logs.
        auto_convert : bool, optional
            Convertit automatiquement en W si possible.
        eta_autowire : bool, optional
            Attache les profils eta(t) automatiquement.
        clip_eta_profile : bool, optional
            Clip eta dans [0, 1].

        Returns
        -------
        int
            Longueur N des profils.

        Notes
        -----
        Cette methode prepare le solver mais ne lance pas la propagation DAG.
        L'appel a `run_vector(self.solver)` reste separe pour rendre visible la
        difference entre preparation des inputs et resolution energetique.
        """
        profiles = self.build_solver_inputs(
            profiles_only=True, verbose=verbose, auto_convert=auto_convert,
        )

        if strict:
            lengths = {k: len(v) for k, v in profiles.items()}
            if len(set(lengths.values())) > 1:
                raise ValueError(f"Profils de longueurs différentes: {lengths}")

        from cgn_model.energy_solver import prepare_state
        N = prepare_state(self.solver, profiles)

        if eta_autowire:
            self.attach_converter_eta_profiles(clip=clip_eta_profile, verbose=verbose)

        return N
    
    # -------- Pipeline: signaux adimensionnels -> convertisseurs variables --------
    def attach_converter_eta_profiles(
        self,
        *,
        clip: bool = True,        # clip η dans [0,1]
        check_len: bool = True,   # vérifie len(η) == N si N connu
        verbose: bool = False,
    ) -> dict[str, str]:
        """
        Autowire des profils eta(t) sur les convertisseurs.

        Parameters
        ----------
        clip : bool, optional
            Clip eta dans [0, 1].
        check_len : bool, optional
            Verifie la longueur si N connu.
        verbose : bool, optional
            Active les logs.

        Returns
        -------
        dict[str, str]
            Mapping conv_id -> eta_source_id.
        """
        if self.signals is None:
            raise RuntimeError("Vessel non initialisé (signals manquants).")

        # N (si déjà fixé par prepare_state)
        N: int | None = None
        for b in self.solver.buses.values():
            if b.net_w is not None:
                N = len(b.net_w)
                break

        # Seuls les signaux adimensionnels sont candidats pour eta(t). Les
        # profils avec unite physique restent dans le chemin d'input classique.
        eta_signals: dict[str, FArray] = {}
        for sid, (arr, unit) in self.signals.items():
            if unit == "-":
                eta_signals[sid] = np.asarray(arr, dtype=np.float64).reshape(-1)

        attached: dict[str, str] = {}

        for conv_id, conv in self.solver.converters.items():
            src = getattr(conv, "eta_source", None)
            if not src:
                continue  # ce convertisseur n'attend pas de profil η

            series = eta_signals.get(src)
            if series is None:
                warnings.warn(f"[eta-autowire] {conv_id}: source '{src}' introuvable → fallback eta_default")
                continue

            if series.ndim != 1:
                raise ValueError(f"[eta-autowire] {conv_id}: eta '{src}' doit être 1D, shape={series.shape}")

            if check_len and N is not None and series.shape[0] != N:
                raise ValueError(
                    f"[eta-autowire] {conv_id}: taille η '{src}' = {series.shape[0]} ≠ N={N}"
                )

            if clip:
                series = np.clip(series, 1e-6, 1.0)

            if not hasattr(conv, "eta_profile"):
                warnings.warn(f"[eta-autowire] {conv_id}: pas d'attribut 'eta_profile' → ignoré")
                continue

            conv.eta_profile = series
            attached[conv_id] = src
            if verbose:
                print(f"[eta-autowire] {conv_id} ← {src} (len={len(series)})")

        return attached

    # --- Pipeline court: inputs + rendements variables, sans run_vector ---
    def build_solver(
        self,
        *,
        verbose: bool = False,
        auto_convert_w_profile: bool = False,
        clip_eta_profile: bool = True,
    ) -> None:
        """
        Orchestration courte pour preparer le solver interne.

        Parameters
        ----------
        verbose : bool, optional
            Affiche les informations de cablage.
        auto_convert_w_profile : bool, optional
            Active la conversion automatique des profils vers W.
        clip_eta_profile : bool, optional
            Borne les profils de rendement eta(t) dans l'intervalle admissible.

        Notes
        -----
        Cette methode applique les inputs au solver et attache les profils de
        rendement variables. Elle ne lance pas `run_vector`.
        """
        self.apply_inputs_to_solver(
            verbose=verbose,
            auto_convert=auto_convert_w_profile,
            eta_autowire=True,                # <- direct ici
            clip_eta_profile=clip_eta_profile,
        )

    # --- Gestion des stockages en sortie du SolverDAG ---
    def tally_storages(
        self,
        *,
        overwrite: bool = True,
        require_inputs_applied: bool = True,
        require_solver_run: bool = False,  # laisse False si tu veux pouvoir tally avant run_vector()
    ) -> dict[str, StorageResult]:
        """
        Construit les StorageResult à partir des bus du solver référencés dans storages_cfg.
        - require_inputs_applied: si True, exige que le solver ait au moins des net_w initialisés (via apply_inputs_to_solver()).
        - require_solver_run: si True, tu peux choisir d'appeler run_vector() avant, pour tallier l'état "résolu".
        Retourne un dict id -> StorageResult et alimente self.storages / self.storages_by_id.
        """
        if self.storages_cfg is None:
            self.storages_cfg = []
        results: dict[str, StorageResult] = {}

        # Vérif minimale d’état solver
        if require_inputs_applied:
            any_init = any(b.net_w is not None for b in self.solver.buses.values())
            if not any_init:
                raise RuntimeError(
                    "tally_storages() : le solver ne semble pas initialisé. "
                    "Appelle d'abord Vessel.apply_inputs_to_solver()."
                )

        for scfg in self.storages_cfg:
            bus = self.solver.buses.get(scfg.bus)
            if bus is None:
                raise KeyError(f"Storage {scfg.id!r}: bus inconnu {scfg.bus!r} dans le solver.")
            if bus.net_w is None:
                raise RuntimeError(
                    f"Storage {scfg.id!r}: bus {scfg.bus!r} n'a pas de net_w. "
                    "As-tu appelé apply_inputs_to_solver() (et éventuellement run_vector()) ?"
                )

            # Compat YAML: le nom canonique est `vector_energy`, mais les
            # anciennes configurations peuvent encore fournir `vecteur`.
            vector_name = getattr(scfg, "vector_energy", None)
            if vector_name is None:
                vector_name = getattr(scfg, "vecteur", None)
            vector_params = getattr(scfg, "vector_params", None)
            vector_params_dict = (
                vector_params.model_dump(exclude_none=True)
                if vector_params is not None and hasattr(vector_params, "model_dump")
                else None
            )
            initial_level = getattr(scfg, "initial_level", None)
            initial_level_dict = (
                initial_level.model_dump(exclude_none=True)
                if initial_level is not None and hasattr(initial_level, "model_dump")
                else None
            )

            res = StorageResult.from_bus(
                id=scfg.id,
                bus_id=scfg.bus,
                bus_net_w=bus.net_w,
                dt=self.dt,
                # Le nom du vecteur est une metadonnee; les conversions viennent
                # des parametres PCI/densite transmis juste en dessous.
                vector=vector_name,
                vector_params=vector_params_dict,
                initial_level=initial_level_dict,
            )
            results[scfg.id] = res

        # Alimente les attributs
        if overwrite or self.storages is None:
            self.storages = dict(results)
        else:
            # merge doux
            self.storages.update(results)

        return results

    def results_dataframe(self, ids: list[str] | None = None):
        """
        Compile un DataFrame des vecteurs principaux (signaux, solver, stockages).

        Parameters
        ----------
        ids : list[str] | None, optional
            Liste d'IDs. Si None, inclut tous les vecteurs disponibles.
            - un signal ou input: "<id>"
            - un convertisseur: "<id>" (ajoute les colonnes in/out)
            - un storage: "<id>" (ajoute toutes les colonnes du storage)

        Returns
        -------
        pandas.DataFrame
            DataFrame avec noms de colonnes plats (IDs uniquement) et suffixe d'unite.
            Les unites sont disponibles dans df.attrs["units"].

        Raises
        ------
        RuntimeError
            Si des donnees necessaires ne sont pas disponibles.
        KeyError
            Si un ID est inconnu.
        ValueError
            Si les longueurs de vecteurs sont incoherentes.
        """
        import pandas as pd  # type: ignore

        columns: dict[str, FArray] = {}
        units: dict[str, str] = {}
        order: list[str] = []
        N: int | None = None

        def _add_col(base: str, arr: FArray, unit: str | None = None) -> str:
            nonlocal N
            a = np.asarray(arr)
            if a.ndim != 1:
                raise ValueError(f"Vecteur '{base}' n'est pas 1D.")
            if N is None:
                N = int(a.shape[0])
            elif int(a.shape[0]) != N:
                raise ValueError(f"Longueurs incoherentes pour '{base}' ({a.shape[0]} vs {N}).")
            name = results_col_name(base, unit)
            if name not in columns:
                columns[name] = a  # type: ignore[assignment]
                order.append(name)
                if unit is not None:
                    units[name] = unit
            return name

        # --- time
        t = self.t
        if t is None:
            if self.signals:
                any_arr = next(iter(self.signals.values()))[0]
                t = np.arange(len(any_arr), dtype=float) * float(self.dt)
            else:
                for inp in self.solver.inputs.values():
                    if inp.profile is not None:
                        t = np.arange(len(inp.profile), dtype=float) * float(self.dt)
                        break
        time_col: str | None = None
        if t is not None:
            time_col = _add_col("time", t, "s")

        # --- signals
        if self.signals is None:
            raise RuntimeError("signals manquants. Construisez le Vessel via from_yaml().")
        profile_ids = set((self.profiles or {}).keys())
        signal_col_by_id: dict[str, str] = {}
        for sig_id, (arr, unit) in self.signals.items():
            prefix = "profile" if sig_id in profile_ids else "adapter"
            c = _add_col(f"{prefix}_{sig_id}", arr, unit)
            signal_col_by_id[sig_id] = c

        # --- solver inputs
        missing_inputs = [i.id for i in self.solver.inputs.values() if i.profile is None]
        input_col_by_id: dict[str, str] = {}
        if missing_inputs:
            pass
        else:
            for inp_id, inp in self.solver.inputs.items():
                c = _add_col(f"input_{inp_id}", inp.profile, "W")  # type: ignore[arg-type]
                input_col_by_id[inp_id] = c

        # --- converters in/out
        missing_convs = [
            c_id for c_id, conv in self.solver.converters.items()
            if getattr(conv, "p_in_w", None) is None or getattr(conv, "p_out_w", None) is None
        ]
        conv_cols_by_id: dict[str, tuple[str, str]] = {}
        if missing_convs:
            pass
        else:
            for conv_id, conv in self.solver.converters.items():
                c_in = _add_col(f"converter_{conv_id}_in", conv.p_in_w, "W")   # type: ignore[arg-type]
                c_out = _add_col(f"converter_{conv_id}_out", conv.p_out_w, "W") # type: ignore[arg-type]
                conv_cols_by_id[conv_id] = (c_in, c_out)

        # --- storages
        storage_cols_by_id: dict[str, list[str]] = {}
        if self.storages is not None:
            for stor_id, res in self.storages.items():
                df = res.to_dataframe()
                s_cols: list[str] = []
                for col in df.columns:
                    if col == "t_s":
                        continue
                    unit = unit_from_storage_col(col)
                    base = strip_storage_unit_suffix(col, unit)
                    c = _add_col(f"storage_{stor_id}_{base}", df[col].to_numpy(), unit)
                    s_cols.append(c)
                storage_cols_by_id[stor_id] = s_cols

        # Quand aucun filtre n'est donne, l'utilisateur demande un export complet:
        # on exige donc que les inputs, convertisseurs et stockages configures
        # aient deja ete calcules.
        if ids is None:
            if t is None:
                raise RuntimeError("Vecteur temps indisponible. Lancez le solver ou construisez les signaux.")
            if missing_inputs:
                raise RuntimeError(
                    "Profiles des inputs solver manquants. Appelez build_solver()/apply_inputs_to_solver()."
                )
            if missing_convs:
                raise RuntimeError(
                    "Resultats des convertisseurs manquants. Lancez run_vector() avant export."
                )
            if (self.storages_cfg and (self.storages is None or len(self.storages) == 0)):
                raise RuntimeError(
                    "Stockages configures mais non calcules. Appelez tally_storages() avant export."
                )

        # La selection accepte a la fois les IDs metier historiques et les noms
        # de colonnes prefixes, afin de garder la compatibilite des notebooks.
        selector_map: dict[str, list[str]] = {}

        def _add_selector(key: str, cols: list[str]) -> None:
            if not cols:
                return
            lst = selector_map.setdefault(key, [])
            for c in cols:
                if c not in lst:
                    lst.append(c)

        if time_col is not None:
            _add_selector("time", [time_col])

        for sig_id, c in signal_col_by_id.items():
            _add_selector(sig_id, [c])        # compat historique
            _add_selector(c, [c])             # id prefixed explicite

        for inp_id, c in input_col_by_id.items():
            _add_selector(inp_id, [c])        # compat historique
            _add_selector(c, [c])             # input_<id>_<unit>

        for conv_id, cols in conv_cols_by_id.items():
            c_in, c_out = cols
            _add_selector(conv_id, [c_in, c_out])                 # compat historique
            _add_selector(f"{conv_id}_in", [c_in])                # compat historique
            _add_selector(f"{conv_id}_out", [c_out])              # compat historique
            _add_selector(f"converter_{conv_id}", [c_in, c_out])  # nouveau prefixe logique

        for stor_id, cols in storage_cols_by_id.items():
            if cols:
                _add_selector(stor_id, cols)                    # compat historique
                _add_selector(f"storage_{stor_id}", cols)       # nouveau prefixe logique

        # --- selection
        if ids is None:
            selected = order
        else:
            selected = []
            selected_set = set()
            unknown = []
            for key in ids:
                cols = selector_map.get(key)
                if cols is None and key in columns:
                    cols = [key]
                if not cols:
                    unknown.append(key)
                    continue
                for c in order:
                    if c in cols and c not in selected_set:
                        selected.append(c)
                        selected_set.add(c)
            if unknown:
                raise KeyError(f"IDs inconnus: {unknown}. Disponibles: {sorted(selector_map.keys())}")

        df = pd.DataFrame({c: columns[c] for c in selected})
        df.attrs["units"] = {c: units[c] for c in selected if c in units}
        return df


# --------------------------- Demo ---------------------------
if __name__ == "__main__":
    
    cfg_txt = """
vessel:
  name: "Vevey"
  vessel_type: "DE"                   # la clé "type" est aussi acceptée

profiles:
  - id: "speed"
    kind: "series"
    unit: "kn"                                # noeud (1 kn = 1.852 km/h)
    data: [0.0, 2.7, 5.4, 13.4, -5.4]         # ou file: "speed.csv"

  - id: "hotel_load"
    kind: "series"
    unit: "W"
    data: [8000, 8200, 7500, 7600, 7800]

adapters:
    # 1) vitesse -> force (polynôme)
  - id: "resistance_from_speed"
    kind: "speed_to_force_poly"
    source: "speed"
    unit_in: "m/s"                    # l’adapter attend m/s
    unit_out: "N"                     # et produit des Newton
    params:
      # exemple ([a0, a1, a2] -> P = a0 + a1*v + a2*v^2)
      coeffs: [-209.0, 1904.4, 531.36, 93.312] # coefs vitesse "m/s" to force "N"
    
    # 2) puissance = F * v (multi-entrées)
  - id: "shaft_power_from_Fv"
    kind: "force_and_speed_to_power"
    # NB: 'source' top-level est ignoré par cet adapter (il utilise 2 sources dans params)
    source: ""  # (juste pour satisfaire le schéma générique)
    unit_in: "" # idem
    unit_out: "W"
    params:
      force_source: "resistance_from_speed"
      speed_source: "speed"
      force_unit_in: "N"
      speed_unit_in: "m/s"
    
    # 3) vitesse -> puissance (polynôme)
  - id: "shaft_power_from_speed"
    kind: "speed_to_power_poly"
    source: "speed"
    unit_in: "m/s"                    # l’adapter attend m/s
    unit_out: "W"                     # et produit des Watts
    params:
      # ici juste 1 degré de plus que la combinaison de 1) + 2)
      coeffs: [0.0, -209.0, 1904.4, 531.36, 93.312]

inputs:
  - id: "shaft_demand"
    bus: "Mechanical:shaft"
    source: "shaft_power_from_Fv"  # via l’adapter (clé ignorée par le solver, utilisé par Vessel)
    sign: "consume"

  - id: "navops"
    bus: "Electrical:main"
    source: "hotel_load"              # direct: déjà en W
    sign: "inject"         # Test avec faux inject pour tester le scale negatif
    scale: -1.0            # voir ci-dessus, ça test aussi le warning

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
    
    # === Test de base de la création de la classe Vessel ===

    cfg = yaml.safe_load(cfg_txt)
    vessel = Vessel.from_yaml(cfg)
    mapping = vessel.build_solver_inputs(verbose=True)
    for k, (bus, arr) in mapping.items():
        print(k, "->", bus, "| len:", len(arr), "| first:", round(float(arr[0]),2), "| max:", round(max(arr),2))

    
    # === Validation de la config en 2 paties, Vessel -> Solveur ===
    
    def validation_init_solver(vessel, solver):
        dct_vessel_solver = vars(vessel.solver)
        dct_solver = vars(solver)
        # Les ID des Graphs ne sont pas identiques
        del dct_vessel_solver["dag"]
        del dct_solver["dag"]
        return dct_vessel_solver == dct_solver
    
    solver = SolverDAG.from_yaml(cfg)
    
    if validation_init_solver(vessel, solver):
        print("\nOK : Les 2 solveurs sont identiques !\n")
    else:
        print("\nATTENTION : Les 2 solveurs sont différents !\n")
    
    
    # === Test de la création des inputs de Vessel vers le Solveur interne ===
    
    cfg = yaml.safe_load(cfg_txt)
    vessel_1 = Vessel.from_yaml(cfg)
    vessel_2 = Vessel.from_yaml(cfg)
    
    # Option 1: juste récupérer les profils prêts
    mapping = vessel_1.build_solver_inputs(profiles_only=True, verbose=True)
    # puis ailleurs:
    from cgn_model.energy_solver import prepare_state
    prepare_state(vessel_1.solver, mapping)
    
    # Option 2: tout faire en une ligne
    vessel_2.apply_inputs_to_solver(verbose=True)
    
    
    
    
    
