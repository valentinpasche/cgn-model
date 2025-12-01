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
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field, ConfigDict
from numpy.typing import NDArray
import numpy as np

from .config import AdapterCfg  # AdapterCfg générique: id, kind, source, unit_in, unit_out, params

# --------- Types ---------
type FArray = NDArray[np.floating]

__all__ = ["AdapterABC", "build_adapter_from_cfg"]

# ============================================================
#                 Conversion d’unités (stricte)
# ============================================================

# Tables "whitelist" par grandeur (→ facteur vers la base)
# Base 'power'  : W
# Base 'speed'  : m/s

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

def _parse_unit(quantity: Literal["power","speed"], u: str) -> tuple[str, float]:
    if quantity == "power":
        cu = _canon_power_unit(u)
        return cu, _POWER_FACTORS[cu]
    else:
        cu = _canon_speed_unit(u)
        return cu, _SPEED_FACTORS[cu]

def convert_unit(
    series: FArray,
    *,
    unit_in: str,
    unit_out: str,
    quantity: Literal["power","speed"],
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
    quantity : {'power','speed'}
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
    base = series * f_in        # vers base (W ou m/s)
    out = base / f_out          # vers unité cible
    return out, u_out

# ============================================================
#                 Base + Registre d’adapters
# ============================================================

# ---- base ABC: Contrat nominal (impl imposée)
class AdapterABC(ABC):
    """
    Transforme un signal (array, unit) -> (array, unit_out).
    'source' : id du profil/adapter en amont (résolu dans Vessel).
    """
    id: str
    source: str
    unit_in: str
    unit_out: str

    @abstractmethod
    def apply(self, series: FArray, unit: str) -> tuple[FArray, str]:
        """
        Parameters
        ----------
        series : FArray
            Signal d'entrée 1D
        unit : str
            Unité effective du signal d'entrée

        Returns
        -------
        (out_series, out_unit) : (FArray, str)
        """
        ...

# ---- registre
class AdapterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

RegistryEntry = tuple[Type[AdapterParams], Callable[[str, str, str, AdapterParams], AdapterABC]]
REGISTRY: dict[str, RegistryEntry] = {}

def register(kind: str, params_model: Type[AdapterParams]):
    """
    Usage:
        @register("poly_speed_to_power", PolySpeedToPowerParams)
        def build(...): ...
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
#                Impl. : Poly vitesse → puissance
# ============================================================

class PolySpeedToPowerParams(AdapterParams):
    coeffs: list[float] = Field(min_length=1)

@dataclass
class PolySpeedToPowerAdapter(AdapterABC):
    """
    P(v) = a0 + a1*v + a2*v^2 + ...  (v en unit_in 'm/s' après conversion)
    Sortie en 'unit_out' de puissance (souvent 'W').
    """
    id: str
    source: str
    unit_in: str    # ex. 'm/s' (attendu par le poly)
    unit_out: str   # ex. 'W'
    coeffs: tuple[float, ...]  # (a0, a1, ..., an)

    def apply(self, series: FArray, unit: str) -> tuple[FArray, str]:
        # 1) Amener l'entrée sur unit_in (vitesse)
        s, _ = convert_unit(series, unit_in=unit, unit_out=self.unit_in, quantity="speed")
        
        # 2) Appliquer le polynôme
        out = np.zeros_like(s, dtype=np.float64)
        p = np.ones_like(s, dtype=np.float64)
        for a in self.coeffs:
            out += a * p
            p *= s

        # 3) S'assurer que la sortie est bien exprimée dans une unité de PUISSANCE
        out, uo = convert_unit(out, unit_in=self.unit_out, unit_out="W", quantity="power")
        return out, uo  # ('W')

@register("poly_speed_to_power", PolySpeedToPowerParams)
def _build_poly_speed_to_power(
    id: str, source: str, unit_in: str, unit_out: str, params: PolySpeedToPowerParams
) -> AdapterABC:
    return PolySpeedToPowerAdapter(
        id=id, source=source, unit_in=unit_in, unit_out=unit_out, coeffs=tuple(params.coeffs)
    )

# ------------------------------------------------------------
