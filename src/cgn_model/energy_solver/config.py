# cgn_model/energy_solver/config.py

"""
Schemas Pydantic pour la configuration du solver DAG.
"""

from typing import Any
from pydantic import BaseModel, Field, StrictStr, ConfigDict, model_validator
from cgn_model.energy_solver.types import Mode

__all__ = ["Cfg"]

# --- Solver ---
class SolverCfg(BaseModel):
    """
    Configuration du solver.

    Attributes
    ----------
    mode : {"forward","inverse"}
        Mode de resolution du DAG.
    """
    model_config = ConfigDict(extra="forbid")
    mode: Mode

# --- Buses ---
_CANON_UNIT = {
    "Electrical": "W",
    "Mechanical": "W",
    "Chemical":   "W",      # plus tard tu pourras passer à "W_LHV" si tu veux distinguer
}

class BusCfg(BaseModel):
    """
    Configuration d'un bus.

    Attributes
    ----------
    id : str
        Identifiant unique.
    carrier : str
        Porteur energetique (Electrical, Mechanical, Chemical, ...).
    unit : str | None
        Unite attendue, optionnelle dans le YAML.
    """
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    carrier: StrictStr | None = None  # optionnelle dans le YAML
    unit: StrictStr | None = None  # optionnelle dans le YAML

    @model_validator(mode="after")
    def _unit_policy(self):
        expected = _CANON_UNIT.get(self.carrier, "W")

        # normalisation tolérante si une unité est fournie
        if self.unit is None:
            self.unit = expected
        else:
            u = self.unit.strip().lower()
            if u in {"w", "watt", "watts"}:
                self.unit = "W"
            elif u == "w_lhv":
                self.unit = "W_LHV"
            else:
                # valeur inconnue -> on force à l’unité canonique du carrier
                self.unit = expected

        # vérif finale : pour l’instant on impose l’unité canonique
        if self.unit != expected:
            raise ValueError(
                f"Unité incohérente pour carrier={self.carrier!r}: "
                f"reçu {self.unit!r}, attendu {expected!r}."
            )
        return self


# --- Inputs ---
class InputCfg(BaseModel):
    """
    Configuration d'un input du solver.

    Attributes
    ----------
    id : str
        Identifiant unique.
    bus : str
        Bus cible.
    """
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    bus: StrictStr

# --- Converters ---
class ConverterCfg(BaseModel):
    """
    Configuration d'un convertisseur.

    Attributes
    ----------
    id : str
        Identifiant unique.
    from_bus : str
        Bus en entree.
    to_bus : str
        Bus en sortie.
    kind : str
        Type de convertisseur (registre).
    params : dict
        Parametres specifiques au kind.
    """
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    from_bus: StrictStr
    to_bus: StrictStr
    kind: StrictStr
    params: dict[str, Any] = Field(default_factory=dict)


# --- Top-level ---
class Cfg(BaseModel):
    """
    Configuration globale du solver DAG.

    Regroupe solver, buses, converters et inputs.
    """
    model_config = ConfigDict(extra="forbid")
    solver: SolverCfg
    buses: list[BusCfg]
    converters: list[ConverterCfg]
    inputs: list[InputCfg]

    @model_validator(mode="after")
    def cross_checks(self):
        bus_ids = {b.id for b in self.buses}

        bad_conv = [c.id for c in self.converters if c.from_bus not in bus_ids or c.to_bus not in bus_ids]
        bad_in   = [i.id for i in self.inputs if i.bus not in bus_ids]
        if bad_conv:
            raise ValueError(f"Convertisseurs référencent des bus inconnus: {bad_conv}")
        if bad_in:
            raise ValueError(f"Inputs référencent des bus inconnus: {bad_in}")

        from collections import Counter
        def dups(xs): return [k for k, v in Counter(xs).items() if v > 1]
        dup = dups([b.id for b in self.buses]) + dups([c.id for c in self.converters]) + dups([i.id for i in self.inputs])
        if dup:
            raise ValueError(f"IDs dupliqués: {dup}")

        return self





