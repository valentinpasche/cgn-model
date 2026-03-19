# cgn_model/vessel_model/config.py

"""
Schemas Pydantic des sections vessel (profiles, adapters, inputs, storages).
"""

from collections import Counter, deque
from typing import Literal, Any, Annotated
from pydantic import BaseModel, StrictStr, ConfigDict, model_validator, Field, field_validator, AliasChoices

type VesselType = Literal["DE", "steam", "undefined"]

__all__ = ["VesselType", "VesselCfg", "ProfileCfg", "AdapterCfg", "InputBindCfg"]


# ---- Adaptateurs multi-sources
# Déclare quels adapters sont multi-entrées et quelles clés params contiennent leurs sources
MULTISOURCE_KINDS: dict[str, tuple[str, ...]] = {
    "force_and_speed_to_power": ("force_source", "speed_source"),
    # ajouter ici d’autres kinds multi-entrées si tu en crées
}

# ---- Vessel / ammont
class VesselCfg(BaseModel):
    """
    Metadonnees du vessel.
    """
    model_config = ConfigDict(extra="forbid")
    name: StrictStr
    vessel_type: VesselType

    @model_validator(mode="after")
    def check_fields(self):
        return self

# Simulation au global
class SimulationCfg(BaseModel):
    """
    Parametres globaux de simulation.

    Attributes
    ----------
    dt : float
        Pas de temps en secondes.
    """
    model_config = ConfigDict(extra="forbid")
    dt: Annotated[float, Field(gt=0)] = 1.0
    
# profiles
class ProfileCfgBase(BaseModel):
    """
    Base commune des profils.

    Attributes
    ----------
    id : str
        Identifiant unique.
    unit : str
        Unite declaree.
    data : list[float] | None
        Serie explicite (si applicable).
    master : bool
        Indique le profil maitre pour la longueur N.
    """
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    unit: StrictStr
    data: list[float] | None = None
    master: bool = False

class ConstantProfileCfg(ProfileCfgBase):
    """
    Profil constant.
    """    
    kind: Literal["constant"]
    value: float | list[float]  # len==1 autorisé

class SeriesProfileCfg(ProfileCfgBase):
    """
    Profil serie explicite.
    """    
    kind: Literal["series"]
    data: list[float]

class FileProfileCfg(ProfileCfgBase):
    """
    Profil charge depuis un fichier CSV.
    """
    model_config = ConfigDict(extra="forbid")
    kind: Literal["file"]
    file: StrictStr
    column: StrictStr | None = None

    # Optionnels avec défauts raisonnables
    sep: str | None = None          # None => auto-détection
    decimal: Literal[".", ","] = "."  # défaut style US
    encoding: StrictStr = "utf-8-sig" # gère BOM Excel
    
    @field_validator("sep")
    @classmethod
    def _norm_sep(cls, v: str | None) -> str | None:
        if v is None:
            return None
        aliases = {"\\t": "\t", "tab": "\t", "tsv": "\t"}
        v = aliases.get(v, v)
        if v not in {",", ";", "\t", "|"}:
            raise ValueError(f"Separateur invalide: {v!r}. Attendu: ',', ';', '\\t', '|', 'tab'.")
        return v

# ---- Horaire CGN, profils inputs
class NavParams(BaseModel):
    """
    Parametres du profil de navigation (MRUA).
    """
    model_config = ConfigDict(extra="forbid")
    # Optionnels (None par défaut), et si fournis: > 0
    acc: Annotated[float, Field(gt=0)] | None = None
    dec: Annotated[float, Field(gt=0)] | None = None
    v_croisiere: Annotated[float, Field(gt=0)] | None = None
    allow_delay: bool | None = None

# 1) modèles stricts
class NavSelectCruise(BaseModel):
    """
    Selection par croisiere.
    """
    model_config = ConfigDict(extra="forbid")
    by: Literal["cruise"]
    cruise_name: StrictStr

class NavSelectCourse(BaseModel):
    """
    Selection par numero de course.
    """
    model_config = ConfigDict(extra="forbid")
    by: Literal["course"]
    course_no: int

class NavSelectLeg(BaseModel):
    """
    Selection par etape (from_port, to_port).
    """
    model_config = ConfigDict(extra="forbid")
    by: Literal["leg"]
    leg: dict[str, StrictStr]  # {from_port,to_port}

NavSelect = Annotated[
    NavSelectCruise | NavSelectCourse | NavSelectLeg,
    Field(discriminator="by")
]

# 2) pré-normalisation dans le conteneur (ici le profil nav_speed)
class NavSpeedProfileCfg(ProfileCfgBase):
    """
    Profil de vitesse construit a partir des horaires CGN.
    """
    model_config = ConfigDict(extra="forbid")
    kind: Literal["nav_speed"]
    unit: StrictStr = "m/s"
    source: StrictStr
    select: NavSelect
    params: NavParams = Field(default_factory=NavParams)

    @field_validator("select", mode="before")
    @classmethod
    def _normalise_select(cls, v: Any) -> Any:
        """
        Autorise les trois clés connues {cruise_name, course_no, leg}
        mais ne garde que celle requise par 'by'. Refuse toute clé inconnue.
        """
        if not isinstance(v, dict):
            return v
        allowed_pool = {"by", "cruise_name", "course_no", "leg"}
        unknown = set(v.keys()) - allowed_pool
        if unknown:
            raise ValueError(f"Clés inconnues dans select: {sorted(unknown)}")

        by = v.get("by")
        if by == "cruise":
            return {"by": "cruise", "cruise_name": v.get("cruise_name")}
        if by == "course":
            return {"by": "course", "course_no": v.get("course_no")}
        if by == "leg":
            return {"by": "leg", "leg": v.get("leg")}
        # Laisse le validateur du discriminant se plaindre si 'by' est invalide
        return v

ProfileCfg = Annotated[
    ConstantProfileCfg | SeriesProfileCfg | FileProfileCfg | NavSpeedProfileCfg,
    Field(discriminator="kind")
]

# adapters
class AdapterCfg(BaseModel):
    """
    Configuration d'un adapter.
    """
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    kind: StrictStr
    source: StrictStr
    unit_in: StrictStr
    unit_out: StrictStr
    params: dict[str, Any] = Field(default_factory=dict)

# bindings input->bus
class InputBindCfg(BaseModel):
    """
    Binding input du solver vers une source de signal.
    """
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    bus: StrictStr
    source: StrictStr  # id d’un profile OU d’un adapter
    sign: Literal["inject", "consume", "as_is"]  # <- requis, pas de défaut
    scale: float | None = None
    
    @field_validator("sign", mode="before")
    @classmethod
    def _norm_sign(cls, v):
        if isinstance(v, str):
            s = v.strip().lower()
            synonyms = {
                # négatif
                "withdraw": "consume",
                "demand":   "consume",
                "load":     "consume",
                "sink":     "consume",
                # positif
                "supply":   "inject",
                "source":   "inject",
                # identique
                "asis":     "as_is",
                "keep":     "as_is",
            }
            return synonyms.get(s, s)
        return v

# ---- Storage + Vector specs optionnel ---

from cgn_model.vessel_model.utils import PCI_Massic_Unit, PCI_Volumic_Unit

class EnergyVectorParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pci_basis: Literal["mass","volume"] | None = None
    pci_value: float | None = Field(ge=0, default=None)
    pci_mass_unit: PCI_Massic_Unit | None = None
    pci_volume_unit: PCI_Volumic_Unit | None = None
    density_kg_m3: float | None = Field(ge=0,default=None)

    @model_validator(mode="after")
    def check_pci_consistency(self):
        """
        Regles de coherence:
        - basis='mass'   => pci_mass_unit obligatoire, pci_volume_unit interdit
        - basis='volume' => pci_volume_unit obligatoire, pci_mass_unit interdit
        - basis absent   => aucune unite PCI ne doit etre renseignee
        - pci_value suit la meme logique que basis
        """
        basis = self.pci_basis

        if basis == "mass":
            if self.pci_mass_unit is None:
                raise ValueError("EnergyVectorParams: 'pci_mass_unit' obligatoire quand pci_basis='mass'.")
            if self.pci_volume_unit is not None:
                raise ValueError("EnergyVectorParams: ne pas renseigner 'pci_volume_unit' quand pci_basis='mass'.")
            if self.pci_value is None:
                raise ValueError("EnergyVectorParams: 'pci_value' obligatoire quand pci_basis='mass'.")

        elif basis == "volume":
            if self.pci_volume_unit is None:
                raise ValueError("EnergyVectorParams: 'pci_volume_unit' obligatoire quand pci_basis='volume'.")
            if self.pci_mass_unit is not None:
                raise ValueError("EnergyVectorParams: ne pas renseigner 'pci_mass_unit' quand pci_basis='volume'.")
            if self.pci_value is None:
                raise ValueError("EnergyVectorParams: 'pci_value' obligatoire quand pci_basis='volume'.")

        else:
            # Pas de base PCI => pas de details PCI
            if self.pci_mass_unit is not None or self.pci_volume_unit is not None or self.pci_value is not None:
                raise ValueError(
                    "EnergyVectorParams: renseignez 'pci_basis' ('mass' ou 'volume') "
                    "avant d'ajouter pci_value / pci_mass_unit / pci_volume_unit."
                )

        return self

class StorageCfg(BaseModel):
    """
    Declaration d'un stockage adosse a un bus du solver.

    Attributes
    ----------
    id : str
        Identifiant du stockage cote vessel.
    bus : str
        Identifiant du bus cote solver.
    vector_energy : str | None
        Identifiant optionnel du vecteur energetique (diesel, H2, battery, ...).
    vector_params : EnergyVectorParams | None
        Parametres optionnels (PCI, densite, base mass/volume).
    """
    model_config = ConfigDict(extra="forbid")

    id: StrictStr
    bus: StrictStr
    vector_energy: StrictStr | None = Field(
        default=None,
        validation_alias=AliasChoices("vector_energy", "vector_name", "vector", "vecteur"),
        serialization_alias="vector_energy",
    )
    vector_params: EnergyVectorParams | None = None

# ---- top level
class VesselSectionsCfg(BaseModel):
    """
    Valide la cohérence des sections 'profiles' / 'adapters' / 'inputs' (hors solver).
    - IDs uniques
    - Sources d'adapters existantes
    - Graphe acyclique (profiles + adapters)
    - Inputs.source référence un signal existant (profile ou adapter)
    """
    model_config = ConfigDict(extra="forbid")
    simulation: SimulationCfg = Field(default_factory=SimulationCfg)
    profiles: list[ProfileCfg] = []
    adapters: list[AdapterCfg] = []
    inputs:   list[InputBindCfg] = []
    storages: list[StorageCfg] = []

    @model_validator(mode="after")
    def cross_checks(self):
        # --- Unicité par section
        def dups(xs): return [k for k, v in Counter(xs).items() if v > 1]

        prof_ids = [p.id for p in self.profiles]
        adap_ids = [a.id for a in self.adapters]
        inp_ids  = [i.id for i in self.inputs]
        stor_ids = [s.id for s in self.storages]

        dup_profiles = dups(prof_ids)
        dup_adapters = dups(adap_ids)
        dup_inputs   = dups(inp_ids)
        dup_storages = dups(stor_ids)

        errs: list[str] = []
        if dup_profiles: errs.append(f"IDs dupliqués dans profiles: {dup_profiles}")
        if dup_adapters: errs.append(f"IDs dupliqués dans adapters: {dup_adapters}")
        if dup_inputs:   errs.append(f"IDs dupliqués dans inputs: {dup_inputs}")
        if dup_storages: errs.append(f"IDs dupliqués dans storages: {dup_storages}")

        # --- Collision d'espace de noms des signaux (profile vs adapter)
        prof_set = set(prof_ids)
        adap_set = set(adap_ids)
        both = sorted(prof_set & adap_set)
        if both:
            errs.append(f"IDs utilisés à la fois comme profile et adapter (collision): {both}")

        # --- Collision d'espace de noms avec storages
        stor_set = set(stor_ids)
        stor_prof = sorted(stor_set & prof_set)
        stor_adap = sorted(stor_set & adap_set)
        if stor_prof:
            errs.append(f"IDs utilisés à la fois comme storage et profile (collision): {stor_prof}")
        if stor_adap:
            errs.append(f"IDs utilisés à la fois comme storage et adapter (collision): {stor_adap}")
        
        # --- Vérif des sources d'adapters
        signal_ids = prof_set | adap_set
        for a in self.adapters:
            req_sources: list[str]
            if a.kind in MULTISOURCE_KINDS:
                # multi-entrées : lire les ids dans params
                keys = MULTISOURCE_KINDS[a.kind]
                missing = [k for k in keys if k not in (a.params or {})]
                if missing:
                    errs.append(f"Adapter {a.id!r} ({a.kind}) params manquants: {missing}")
                    continue
                req_sources = [str(a.params[k]) for k in keys]
            else:
                # mono-entrée
                if not isinstance(a.source, str) or not a.source:
                    errs.append(f"Adapter {a.id!r}: 'source' invalide/absente")
                    continue
                req_sources = [a.source]

            # chaque source doit exister
            not_found = [s for s in req_sources if s not in signal_ids]
            if not_found:
                errs.append(f"Adapter {a.id!r}: sources inconnues {not_found}")

            # pas d’auto-référence
            if a.id in req_sources:
                errs.append(f"Adapter {a.id!r}: s’auto-référence comme source")

        # --- Graphe acyclique (Kahn)
        # noeuds = profiles + adapters ; arêtes = source -> adapter
        indeg: dict[str, int] = {sid: 0 for sid in signal_ids}
        adj: dict[str, list[str]] = {sid: [] for sid in signal_ids}

        def add_edge(u: str, v: str):  # u(source) -> v(adapter)
            adj[u].append(v)
            indeg[v] += 1

        # edges
        for a in self.adapters:
            if a.kind in MULTISOURCE_KINDS:
                keys = MULTISOURCE_KINDS[a.kind]
                if all(k in (a.params or {}) for k in keys):
                    for k in keys:
                        s = str(a.params[k])
                        if s in signal_ids:
                            add_edge(s, a.id)
            else:
                if isinstance(a.source, str) and a.source in signal_ids:
                    add_edge(a.source, a.id)

        # Kahn topo
        q = deque([n for n, d in indeg.items() if d == 0])
        seen = 0
        while q:
            u = q.popleft()
            seen += 1
            for v in adj[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)

        if seen != len(signal_ids):
            errs.append("Cycle détecté dans (profiles+adapters). Vérifie les dépendances.")

        # --- Inputs.source doit exister
        for i in self.inputs:
            if i.source not in signal_ids:
                errs.append(f"Input {i.id!r}: source inconnue {i.source!r}")

        if errs:
            raise ValueError("Vessel sections invalides:\n- " + "\n- ".join(errs))

        return self



















