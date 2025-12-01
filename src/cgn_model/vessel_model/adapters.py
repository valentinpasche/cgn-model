# cgn_model/vessel_model/adapters.py

"""
Adapters runtime + registre

But
----
Transformer des profils *bruts* (ex. vitesse en kn) en signaux utilisables par le solver (W).
Chaque adapter :
  - lit une source (id d'un profile ou d'un autre adapter),
  - convertit l'unité d'entrée vers une unité attendue,
  - applique une transformation,
  - produit (array, unit_out) — typiquement 'W' pour alimenter un Input du solver.

API publique (minimale)
-----------------------
- AdapterABC               : contrat runtime
- AdapterParams            : base Pydantic pour les params
- register(kind, Model)    : décorateur pour enregistrer un adapter
- build_adapter_from_cfg() : construit un adapter depuis AdapterCfg
- convert_unit()           : conversion d’unités stricte (sensible à la casse SI)

Adapter fourni
--------------
- kind="poly_speed_to_power" : P = a0 + a1*v + a2*v^2 + ..., avec v en 'm/s' (converti)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Type, Literal
from abc import ABC

from pydantic import BaseModel, Field, ConfigDict, StrictStr
from numpy.typing import NDArray
import numpy as np

from .config import AdapterCfg  # AdapterCfg générique: id, kind, source, unit_in, unit_out, params

type FArray = NDArray[np.floating]

__all__ = ["AdapterABC", "build_adapter_from_cfg"]

# ============================================================
# ----            Conversion d’unités (stricte)
# ============================================================

# Tables "whitelist" par grandeur (→ facteur vers la base)
# Base 'power'  : W
# Base 'speed'  : m/s
# Base 'force'  : N

_POWER_FACTORS = {
    "W": 1.0,
    "kW": 1e3,
    "MW": 1e6,
    "GW": 1e9,
    "mW": 1e-3,
    "µW": 1e-6,  # micro (unicode)
    "uW": 1e-6,  # tolérance 'u' pour micro
}
_POWER_SYNONYMS = {
    # tolérance textuelle (casse exacte)
    "Watt": "W", "Watts": "W", "watt": "W", "watts": "W", "w": "W",
}

_SPEED_FACTORS = {
    "m/s": 1.0,
    "km/h": 1000.0 / 3600.0,
    "kn": 1852.0 / 3600.0,   # knot (nœud) — 1 NM = 1852 m
    "kt": 1852.0 / 3600.0,   # alias
    "kts": 1852.0 / 3600.0,  # alias
}
_SPEED_SYNONYMS = {
    "mps": "m/s",
}

_FORCE_FACTORS = {
    "N": 1.0,
    "kN": 1e3,
    "MN": 1e6,
    "GN": 1e9,
    "mN": 1e-3,
}
_FORCE_SYNONYMS = {
    # tolérance textuelle (casse exacte)
    "Newton": "N", "newton": "N", "Newtons": "N", "newtons": "N",
}

def _canon_power_unit(u: str) -> str:
    u = u.strip()
    if u in _POWER_FACTORS:
        return u
    if u in _POWER_SYNONYMS:
        return _POWER_SYNONYMS[u]
    # On REFUSE les minuscules ambiguës ('mw', 'kw', ...) → l'utilisateur doit écrire 'mW', 'kW', ...
    raise ValueError(
        f"Unité de puissance non reconnue/ambigüe: {u!r}. "
        "Exemples valides: 'W', 'kW', 'MW', 'mW', 'µW'."
    )

def _canon_speed_unit(u: str) -> str:
    u = u.strip()
    if u in _SPEED_FACTORS:
        return u
    if u in _SPEED_SYNONYMS:
        return _SPEED_SYNONYMS[u]
    # Tolérances utiles
    if u.lower() in {"kn", "kt", "kts"}:
        return "kn"
    if u.lower() == "mps":
        return "m/s"
    if u.lower() == "km/h":
        return "km/h"
    raise ValueError(
        f"Unité de vitesse non reconnue: {u!r}. "
        "Exemples valides: 'm/s', 'km/h', 'kn'."
    )

def _canon_force_unit(u: str) -> str:
    u = u.strip()
    if u in _FORCE_FACTORS:
        return u
    if u in _FORCE_SYNONYMS:
        return _FORCE_SYNONYMS[u]
    raise ValueError(
        f"Unité de force non reconnue/ambigüe: {u!r}. "
        "Exemples valides: 'N', 'kN', 'MN', 'GN', 'mN'."
    )

def _parse_unit(quantity: Literal["power","speed", "force"], u: str) -> tuple[str, float]:
    if quantity == "power":
        cu = _canon_power_unit(u)
        return cu, _POWER_FACTORS[cu]
    elif quantity == "speed":
        cu = _canon_speed_unit(u)
        return cu, _SPEED_FACTORS[cu]
    elif quantity == "force":
        cu = _canon_force_unit(u)
        return cu, _FORCE_FACTORS[cu]
    else:
        raise NotImplementedError(
            "Qantitée non implémentée."
            "Valides: 'power', 'speed', 'force'."
        )

def convert_unit(
    series: FArray,
    *,
    unit_in: str,
    unit_out: str,
    quantity: Literal["power","speed","force"],
) -> tuple[FArray, str]:
    """
    Conversion stricte et sûre (sensible à la casse SI).

    Parameters
    ----------
    series : FArray
        Signal 1D
    unit_in : str
        Unité actuelle
    unit_out : str
        Unité cible
    quantity : {'power','speed','froce'}
        Domaine physique (détermine les tables)

    Returns
    -------
    (series_out, unit_out)

    Notes
    -----
    - Base 'power' : W ; base 'speed' : m/s.
    - Refuse les écritures ambiguës ('mw', 'kw' en minuscules).
    """
    u_in, f_in = _parse_unit(quantity, unit_in)
    u_out, f_out = _parse_unit(quantity, unit_out)
    if u_in == u_out:
        return series, u_out
    base = series * f_in        # vers base (W ou m/s, etc.)
    out = base / f_out          # vers unité cible
    return out, u_out

# ============================================================
# ----            Base + Registre d’adapters
# ============================================================

# ---- base ABC: Contrat nominal (impl imposée)
class AdapterABC(ABC):
    """
    Transforme des signaux en (array, unit_out).
    - Mono-entrée : implémente `apply`.
    - Multi-entrées : implémente `required_sources` + `apply_multi`.
    
    Attention : Il faut déclarer les adapters multi-entrées et les clés que
    params contiennent leurs sources dans le fichier `vessel_model/config.py`
    """
    id: str
    source: str         # id mono-entrée (ignoré par multi si souhaité)
    unit_in: str
    unit_out: str

    def required_sources(self) -> list[str]:
        """Par défaut: mono-entrée -> une seule source."""
        return [self.source]

    def apply(self, series: FArray, unit: str) -> tuple[FArray, str]:
        """
        Implémentation par défaut: non supporté.
        Les adapters mono-entrée doivent surcharger cette méthode.
        """
        raise NotImplementedError(f"{type(self).__name__}.apply() non implémenté (mono-entrée).")

    def apply_multi(self, inputs: dict[str, tuple[FArray, str]]) -> tuple[FArray, str]:
        """
        Implémentation par défaut: fallback mono-entrée — prend self.source dans inputs.
        Les adapters multi-entrées doivent surcharger cette méthode.
        """
        try:
            series, unit = inputs[self.source]
        except KeyError:
            raise KeyError(f"Source manquante: {self.source!r} pour {self.id!r}")
        return self.apply(series, unit)

class AdapterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

# ---- registre
RegistryEntry = tuple[Type[AdapterParams], Callable[[str, str, str, AdapterParams], AdapterABC]]
REGISTRY: dict[str, RegistryEntry] = {}

def register(kind: str, params_model: Type[AdapterParams]):
    """
    Usage:
        @register("speed_to_power_poly", SpeedToPowerPolyParams)
        def build(...): ...
        
    Convention de nommage :
        kind: "<qin>_to_<qout>_<méthode>"
        Exemples : speed_to_force_poly, force_to_power_mul, speed_to_power_poly.
    """
    def deco(builder: Callable[[str, str, str, AdapterParams], AdapterABC]):
        REGISTRY[kind] = (params_model, builder)
        return builder
    return deco

# ---- builder générique (utilisé par Vessel)
def build_adapter_from_cfg(c: AdapterCfg) -> AdapterABC:
    """
    c: AdapterCfg (id, kind, source, unit_in, unit_out, params)
    """
    try:
        ParamsModel, builder = REGISTRY[c.kind]
    except KeyError:
        avail = ", ".join(sorted(REGISTRY.keys()))
        raise NotImplementedError(f"Adapter kind inconnu: {c.kind!r}. Kinds dispo: {avail}")
    params = ParamsModel.model_validate(c.params or {})
    return builder(c.id, c.source, c.unit_in, c.unit_out, params)

# ============================================================
# ---- Impl 1 — vitesse -> puissance , poly (mono-entrée)
# ============================================================

class SpeedToPowerPolyParams(AdapterParams):
    coeffs: list[float] = Field(min_length=1)

@dataclass
class SpeedToPowerPolyAdapter(AdapterABC):
    id: str
    source: str
    unit_in: str    # ex 'm/s'
    unit_out: str   # ex 'W'
    coeffs: tuple[float, ...]  # a0, a1, ...

    def apply(self, series: FArray, unit: str) -> tuple[FArray, str]:
        # 1) vitesse -> unit_in
        s, _ = convert_unit(series, unit_in=unit, unit_out=self.unit_in, quantity="speed")
        # 2) poly
        out = np.zeros_like(s, dtype=np.float64)
        p = np.ones_like(s, dtype=np.float64)
        for a in self.coeffs:
            out += a * p
            p *= s
        # 3) puissance -> 'W'
        out, uo = convert_unit(out, unit_in=self.unit_out, unit_out="W", quantity="power")
        return out, uo

@register("speed_to_power_poly", SpeedToPowerPolyParams)
def _build_speed_to_power_ploy(id: str, source: str, unit_in: str, unit_out: str, p: SpeedToPowerPolyParams) -> AdapterABC:
    return SpeedToPowerPolyAdapter(id=id, source=source, unit_in=unit_in, unit_out=unit_out, coeffs=tuple(p.coeffs))

# ============================================================
# ---- Impl 2 — puissance = force * vitesse (multi-entrées)
# Déclarer quels adapters sont multi-entrées et quelles clés params contiennent leurs sources,
# dans le fichier de config du vessel_model !!!
# ============================================================

class ForceAndSpeedToPowerParams(AdapterParams):
    force_source: StrictStr
    speed_source: StrictStr
    # unités attendues en entrée (avant conversion)
    force_unit_in: StrictStr = "N"
    speed_unit_in: StrictStr = "m/s"
    # unité de sortie déclarée
    unit_out: StrictStr = "W"

@dataclass
class ForceAndSpeedToPowerAdapter(AdapterABC):
    """
    P = F * v
    Cet adapter ignore 'source' top-level d'AdapterCfg et utilise 2 sources dans Params.
    """
    id: str
    # champs hérités mais non utilisés ici:
    source: str
    unit_in: str
    unit_out: str

    force_source: str
    speed_source: str
    force_unit_in: str
    speed_unit_in: str
    out_unit: str  # (souvent 'W')

    # multi-entrées
    def required_sources(self) -> list[str]:
        return [self.force_source, self.speed_source]

    def apply_multi(self, inputs: dict[str, tuple[FArray, str]]) -> tuple[FArray, str]:
        try:
            f_series, f_unit = inputs[self.force_source]
            v_series, v_unit = inputs[self.speed_source]
        except KeyError as e:
            raise KeyError(f"Source manquante pour adapter {self.id!r}: {e.args[0]!r}")

        f_si, _ = convert_unit(f_series, unit_in=f_unit, unit_out=self.force_unit_in, quantity="force")  # -> N
        v_si, _ = convert_unit(v_series, unit_in=v_unit, unit_out=self.speed_unit_in, quantity="speed")  # -> m/s

        p = f_si * v_si  # W en SI
        p_out, uo = convert_unit(p, unit_in="W", unit_out=self.out_unit, quantity="power")
        return p_out, uo

@register("force_and_speed_to_power", ForceAndSpeedToPowerParams)
def _build_force_and_speed_to_power(id: str, source: str, unit_in: str, unit_out: str, p: ForceAndSpeedToPowerParams) -> AdapterABC:
    # 'source' et 'unit_in' top-level ne sont pas utilisés ici (multi-entrées)
    return ForceAndSpeedToPowerAdapter(
        id=id, source=source, unit_in=unit_in, unit_out=unit_out,
        force_source=p.force_source, speed_source=p.speed_source,
        force_unit_in=p.force_unit_in, speed_unit_in=p.speed_unit_in,
        out_unit=p.unit_out,
    )

# ============================================================
# ---- Impl 3 — vitesse -> force , poly (mono-entrée)
# ============================================================

class SpeedToForcePolyParams(AdapterParams):
    coeffs: list[float] = Field(min_length=1)

@dataclass
class SpeedToForcePoly(AdapterABC):
    """
    F(v) = a0 + a1*v + a2*v^2 + ... 
    Entrée: vitesse (unit_in, p.ex. 'm/s'), Sortie: force ('N').
    """
    id: str
    source: str
    unit_in: str     # ex. 'm/s'
    unit_out: str    # ex. 'N'
    coeffs: tuple[float, ...]

    def apply(self, series: FArray, unit: str) -> tuple[FArray, str]:
        # 1) vitesse -> unit_in
        v, _ = convert_unit(series, unit_in=unit, unit_out=self.unit_in, quantity="speed")
        # 2) polynôme
        out = np.zeros_like(v, dtype=np.float64)
        p = np.ones_like(v, dtype=np.float64)
        for a in self.coeffs:
            out += a * p
            p *= v
        # 3) force -> 'N' (ou unit_out)
        out, uo = convert_unit(out, unit_in=self.unit_out, unit_out="N", quantity="force")
        return out, uo

@register("speed_to_force_poly", SpeedToForcePolyParams)
def _build_speed_to_force_poly(id: str, source: str, unit_in: str, unit_out: str, p: SpeedToForcePolyParams) -> AdapterABC:
    return SpeedToForcePoly(
        id=id, source=source, unit_in=unit_in, unit_out=unit_out, coeffs=tuple(p.coeffs)
    )


