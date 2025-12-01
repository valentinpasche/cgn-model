# cgn_model/vessel_model/config.py

from collections import Counter, deque
from typing import Literal, Any
from pydantic import BaseModel, StrictStr, ConfigDict, model_validator, Field

type VesselType = Literal["DE", "steam", "undefined"]

__all__ = ["VesselType", "VesselCfg", "ProfileCfg", "AdapterCfg", "InputBindCfg"]


# Déclare quels adapters sont multi-entrées et quelles clés params contiennent leurs sources
MULTISOURCE_KINDS: dict[str, tuple[str, ...]] = {
    "force_and_speed_to_power": ("force_source", "speed_source"),
    # ajouter ici d’autres kinds multi-entrées si tu en crées
}


class VesselCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: StrictStr
    vessel_type: VesselType

    @model_validator(mode="after")
    def check_fields(self):
        return self
    
# profiles
class ProfileCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    unit: StrictStr
    data: list[float] | None = None
    file: StrictStr | None = None

# adapters
class AdapterCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    kind: StrictStr
    source: StrictStr
    unit_in: StrictStr
    unit_out: StrictStr
    params: dict[str, Any] = Field(default_factory=dict)

# bindings input->bus
class InputBindCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    bus: StrictStr
    source: StrictStr  # id d’un profile OU d’un adapter

# top level
class VesselSectionsCfg(BaseModel):
    """
    Valide la cohérence des sections 'profiles' / 'adapters' / 'inputs' (hors solver).
    - IDs uniques
    - Sources d'adapters existantes
    - Graphe acyclique (profiles + adapters)
    - Inputs.source référence un signal existant (profile ou adapter)
    """
    model_config = ConfigDict(extra="forbid")

    profiles: list[ProfileCfg] = []
    adapters: list[AdapterCfg] = []
    inputs:   list[InputBindCfg] = []

    @model_validator(mode="after")
    def cross_checks(self):
        # --- Unicité par section
        def dups(xs): return [k for k, v in Counter(xs).items() if v > 1]

        prof_ids = [p.id for p in self.profiles]
        adap_ids = [a.id for a in self.adapters]
        inp_ids  = [i.id for i in self.inputs]

        dup_profiles = dups(prof_ids)
        dup_adapters = dups(adap_ids)
        dup_inputs   = dups(inp_ids)

        errs: list[str] = []
        if dup_profiles: errs.append(f"IDs dupliqués dans profiles: {dup_profiles}")
        if dup_adapters: errs.append(f"IDs dupliqués dans adapters: {dup_adapters}")
        if dup_inputs:   errs.append(f"IDs dupliqués dans inputs: {dup_inputs}")

        # --- Collision d'espace de noms des signaux (profile vs adapter)
        prof_set = set(prof_ids)
        adap_set = set(adap_ids)
        both = sorted(prof_set & adap_set)
        if both:
            errs.append(f"IDs utilisés à la fois comme profile et adapter (collision): {both}")

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
