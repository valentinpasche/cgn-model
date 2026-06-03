# cgn_model/vessel_model/adapters.py

"""
Adapters runtime du `Vessel` et registre de construction.

Role du module
--------------
Un adapter transforme un signal metier en signal utilisable par le solver. Il
lit une ou plusieurs sources deja materialisees par `Vessel` (profils bruts ou
sorties d'autres adapters), convertit les unites vers l'unite attendue, applique
une transformation, puis retourne `(array, unit_out)`.

La convention de signe n'est pas appliquee ici. Les adapters produisent des
grandeurs physiques dans leur unite de sortie; le signe `consume` / `inject` /
`as_is` est applique plus tard par les bindings d'inputs dans `Vessel`.

Adapters fournis
----------------
- `speed_to_power_poly` : vitesse -> puissance, polynome `P(v)`.
- `force_and_speed_to_power` : force et vitesse -> puissance, produit `P = F*v`.
- `speed_to_force_poly` : vitesse -> force, polynome `F(v)`.
- `speed_to_eta_poly` : vitesse -> rendement adimensionnel `eta(v)`.
- `power_to_power_poly` : puissance -> puissance, correction empirique ou
  passage direct d'un profil de puissance vers un signal connectable.

Unites
------
`convert_unit` applique des conversions strictes par grandeur physique :

- puissance : base W;
- vitesse : base m/s;
- force : base N.

Les ecritures SI ambigues sont refusees, par exemple `mw` au lieu de `mW` ou
`MW`.

Registre et extension
---------------------
Le registre interne `REGISTRY` mappe `kind -> (ParamsModel, builder)`.
`build_adapter_from_cfg(c)` lit `c.kind`, valide `c.params` avec le modele
Pydantic associe, puis appelle le builder.

Pour ajouter un adapter mono-source :

1. definir un modele de parametres derive de `AdapterParams`;
2. implementer une classe derivee de `AdapterABC` avec `apply(series, unit)`;
3. enregistrer un builder avec `@register("nouveau_kind", ParamsModel)`.

Pour un adapter multi-source, surcharger `required_sources()` et `apply_multi()`.
Le `kind` multi-source doit aussi etre declare dans `vessel_model.config`
(`MULTISOURCE_KINDS`) afin que la validation YAML connaisse les cles de sources
attendues dans `params`.

Si ce nouveau adaptateur doit aussi etre cree depuis l'interface web ou
documente pour les utilisateurs YAML, il faudra mettre a jour les couches UI,
les exemples et la documentation externe correspondants.

Bonnes pratiques
----------------
- Garder les adapters sans effet de bord.
- Ne pas appliquer de convention de signe dans un adapter; la laisser aux
  `InputBind`.
- Preferer des noms de `kind` explicites et stables.
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

__all__ = [
    "convert_unit",
    "AdapterABC",
    "build_adapter_from_cfg",
]

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
    Conversion stricte d'unites (sensible a la casse SI).
    Parameters
    ----------
    series : FArray
        Signal 1D.
    unit_in : str
        Unite actuelle (ex. "kW", "m/s", "N").
    unit_out : str
        Unite cible.
    quantity : {'power','speed','force'}
        Domaine physique (determine les tables).
    Returns
    -------
    series_out : FArray
        Signal converti.
    unit_out : str
        Unite finale (canonisee).
    Notes
    -----
    - Base "power" : W ; base "speed" : m/s ; base "force" : N.
    - Refuse les ecritures ambigues ('mw', 'kw' en minuscules).
    Examples
    --------
    >>> import numpy as np
    >>> v = np.array([0.0, 10.0])
    >>> out, u = convert_unit(v, unit_in="km/h", unit_out="m/s", quantity="speed")
    >>> u
    'm/s'
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
    Contrat d'adapter runtime (mono-entree ou multi-entrees).
    Un adapter :
    - lit une ou plusieurs sources (profiles/adapters),
    - convertit les unites,
    - applique une transformation,
    - produit un signal (array, unit_out), typiquement en W.
    Notes
    -----
    - Mono-entree : implementer apply.
    - Multi-entrees : implementer required_sources + apply_multi.
    - Declarer les kinds multi-entrees dans vessel_model/config.py
      (liste MULTISOURCE_KINDS).
    Examples
    --------
    Adapter mono-entree minimal :
    >>> from dataclasses import dataclass
    >>> @dataclass
    ... class SpeedToPower(AdapterABC):
    ...     id: str
    ...     source: str
    ...     unit_in: str
    ...     unit_out: str
    ...     def apply(self, series, unit):
    ...         s, _ = convert_unit(series, unit_in=unit, unit_out=self.unit_in, quantity="speed")
    ...         p = s * 10.0
    ...         return convert_unit(p, unit_in="W", unit_out=self.unit_out, quantity="power")
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
    """
    Base Pydantic pour les parametres d'adapters.
    Notes
    -----
    - extra="forbid" empeche les fautes de frappe dans le YAML.
    """
    model_config = ConfigDict(extra="forbid")

# ---- registre
RegistryEntry = tuple[Type[AdapterParams], Callable[[str, str, str, AdapterParams], AdapterABC]]
REGISTRY: dict[str, RegistryEntry] = {}

def register(kind: str, params_model: Type[AdapterParams]):
    """
    Enregistre un adapter dans le registre global.
    Parameters
    ----------
    kind : str
        Identifiant du type d'adapter (ex. "speed_to_power_poly").
    params_model : type[AdapterParams]
        Modele Pydantic pour valider les parametres.
    Notes
    -----
    Convention de nommage :
      "<qin>_to_<qout>_<methode>"
      Exemples : "speed_to_force_poly", "force_to_power_mul".
    Examples
    --------
    >>> @register("speed_to_power_poly", SpeedToPowerPolyParams)
    ... def build(id, source, unit_in, unit_out, p):
    ...     return SpeedToPowerPolyAdapter(
    ...         id=id, source=source, unit_in=unit_in, unit_out=unit_out,
    ...         coeffs=tuple(p.coeffs), clip_min=p.clip_min,
    ...     )
    """
    def deco(builder: Callable[[str, str, str, AdapterParams], AdapterABC]):
        REGISTRY[kind] = (params_model, builder)
        return builder
    return deco

# ---- builder générique (utilisé par Vessel)
def build_adapter_from_cfg(c: AdapterCfg) -> AdapterABC:
    """
    Construit un adapter a partir d'un AdapterCfg.
    Parameters
    ----------
    c : AdapterCfg
        Configuration validee (id, kind, source, unit_in, unit_out, params).
    Returns
    -------
    AdapterABC
        Instance d'adapter prete a etre utilisee.
    Raises
    ------
    NotImplementedError
        Si kind n'est pas enregistre.
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
    clip_min: float | None = 0.0  # par défaut on clippe à 0

@dataclass
class SpeedToPowerPolyAdapter(AdapterABC):
    """
    Adapter vitesse -> puissance via polynome.

    Parameters
    ----------
    coeffs : tuple[float, ...]
        Coefficients (a0, a1, a2, ...).
    unit_in : str
        Unite attendue en entree (ex. "m/s").
    unit_out : str
        Unite de sortie (ex. "W").
    clip_min : float | None
        Valeur minimale (None pour ne pas clipper).

    Notes
    -----
    - P(v) = a0 + a1*v + a2*v^2 + ...
    - Conversion d'unites automatique vers unit_in.
    - Les coefficients sont appliques dans l'unite `unit_in`; leur domaine de
      validite physique doit venir de la configuration ou de la documentation
      metier externe.
    """
    id: str
    source: str
    unit_in: str    # ex 'm/s'
    unit_out: str   # ex 'W'
    coeffs: tuple[float, ...]  # a0, a1, ...
    clip_min: float | None

    def apply(self, series: FArray, unit: str) -> tuple[FArray, str]:
        # 1) vitesse -> unit_in
        s, _ = convert_unit(series, unit_in=unit, unit_out=self.unit_in, quantity="speed")
        # TODO: documenter dans les donnees projet l'origine, l'unite d'entree
        # et le domaine de validite des coefficients polynomiaux.
        # 2) poly
        out = np.zeros_like(s, dtype=np.float64)
        p = np.ones_like(s, dtype=np.float64)
        for a in self.coeffs:
            out += a * p
            p *= s
        # 3) clip
        if self.clip_min is not None:
            out = np.clip(out, float(self.clip_min), None)
        # 4) puissance native -> unit_out déclarée
        out, uo = convert_unit(out, unit_in="W", unit_out=self.unit_out, quantity="power")
        return out, uo

@register("speed_to_power_poly", SpeedToPowerPolyParams)
def _build_speed_to_power_poly(
        id: str, source: str, unit_in: str, unit_out: str, p: SpeedToPowerPolyParams
) -> AdapterABC:
    return SpeedToPowerPolyAdapter(
        id=id, source=source, unit_in=unit_in, unit_out=unit_out,
        coeffs=tuple(p.coeffs), clip_min=p.clip_min
    )
# ============================================================
# ---- Impl 2 — puissance = force * vitesse (multi-entrées)
# Déclarer quels adapters sont multi-entrées et quelles clés params contiennent leurs sources,
# dans le fichier de config du vessel_model !!!
# ============================================================


class ForceAndSpeedToPowerParams(AdapterParams):
    force_source: StrictStr
    speed_source: StrictStr
    force_unit_in: StrictStr = "N"
    speed_unit_in: StrictStr = "m/s"
    clip_min: float | None = 0.0

@dataclass
class ForceAndSpeedToPowerAdapter(AdapterABC):
    """
    Adapter multi-entrees: puissance = force * vitesse.

    Parameters
    ----------
    force_source : str
        ID de la source force.
    speed_source : str
        ID de la source vitesse.
    force_unit_in : str
        Unite attendue pour la force (ex. "N").
    speed_unit_in : str
        Unite attendue pour la vitesse (ex. "m/s").
    unit_out : str
        Unite de sortie (ex. "W").
    clip_min : float | None
        Valeur minimale (None pour ne pas clipper).

    Notes
    -----
    - Ignore source top-level d'AdapterCfg.
    - P = F * v (en SI, W).
    - La convention de signe n'est pas appliquee dans l'adapter; elle est
      appliquee plus tard par le binding d'input du `Vessel`.
    """
    id: str
    source: str
    unit_in: str
    unit_out: str   # <= une seule fois

    force_source: str
    speed_source: str
    force_unit_in: str
    speed_unit_in: str
    clip_min: float | None

    def required_sources(self) -> list[str]:
        return [self.force_source, self.speed_source]

    def apply_multi(self, inputs: dict[str, tuple[FArray, str]]) -> tuple[FArray, str]:
        f_series, f_unit = inputs[self.force_source]
        v_series, v_unit = inputs[self.speed_source]
        f_si, _ = convert_unit(f_series, unit_in=f_unit, unit_out=self.force_unit_in, quantity="force")
        v_si, _ = convert_unit(v_series, unit_in=v_unit, unit_out=self.speed_unit_in, quantity="speed")
        p_out = f_si * v_si  # en W (SI)
        if self.clip_min is not None:
            p_out = np.clip(p_out, float(self.clip_min), None)
        # retourne dans l'unité déclarée
        p_out, uo = convert_unit(p_out, unit_in="W", unit_out=self.unit_out, quantity="power")
        return p_out, uo

@register("force_and_speed_to_power", ForceAndSpeedToPowerParams)
def _build_force_and_speed_to_power(
        id: str, source: str, unit_in: str, unit_out: str, p: ForceAndSpeedToPowerParams
) -> AdapterABC:
    return ForceAndSpeedToPowerAdapter(
        id=id, source=source, unit_in=unit_in, unit_out=unit_out,
        force_source=p.force_source, speed_source=p.speed_source,
        force_unit_in=p.force_unit_in, speed_unit_in=p.speed_unit_in,
        clip_min=p.clip_min,
    )


# ============================================================
# ---- Impl 3 — vitesse -> force , poly (mono-entrée)
# ============================================================

class SpeedToForcePolyParams(AdapterParams):
    coeffs: list[float] = Field(min_length=1)
    clip_min: float | None = 0.0  # par défaut on clippe à 0

@dataclass
class SpeedToForcePoly(AdapterABC):
    """
    Adapter vitesse -> force via polynome.

    Parameters
    ----------
    coeffs : tuple[float, ...]
        Coefficients (a0, a1, a2, ...).
    unit_in : str
        Unite attendue en entree (ex. "m/s").
    unit_out : str
        Unite de sortie (ex. "N").
    clip_min : float | None
        Valeur minimale (None pour ne pas clipper).

    Notes
    -----
    - F(v) = a0 + a1*v + a2*v^2 + ...
    - Conversion d'unites automatique vers unit_in.
    """
    id: str
    source: str
    unit_in: str     # ex. 'm/s'
    unit_out: str    # ex. 'N'
    coeffs: tuple[float, ...]
    clip_min: float | None

    def apply(self, series: FArray, unit: str) -> tuple[FArray, str]:
        # 1) vitesse -> unit_in
        v, _ = convert_unit(series, unit_in=unit, unit_out=self.unit_in, quantity="speed")
        # TODO: documenter dans les donnees projet l'origine, l'unite d'entree
        # et le domaine de validite des coefficients polynomiaux.
        # 2) polynôme
        out = np.zeros_like(v, dtype=np.float64)
        p = np.ones_like(v, dtype=np.float64)
        for a in self.coeffs:
            out += a * p
            p *= v
        if self.clip_min is not None:
            out = np.clip(out, float(self.clip_min), None)
        out, uo = convert_unit(out, unit_in="N", unit_out=self.unit_out, quantity="force")
        return out, uo

@register("speed_to_force_poly", SpeedToForcePolyParams)
def _build_speed_to_force_poly(
        id: str, source: str, unit_in: str, unit_out: str, p: SpeedToForcePolyParams
) -> AdapterABC:
    return SpeedToForcePoly(
        id=id, source=source, unit_in=unit_in, unit_out=unit_out,
        coeffs=tuple(p.coeffs), clip_min=p.clip_min,
    )

# ============================================================
# ---- Impl 4 — vitesse -> rendement , poly (mono-entrée), pour convertisseur solverDag, etc.
# ============================================================

class SpeedToEtaPolyParams(AdapterParams):
    coeffs: list[float] = Field(min_length=1)

@dataclass
class SpeedToEtaPoly(AdapterABC):
    """
    Adapter vitesse -> rendement via polynome.

    Parameters
    ----------
    coeffs : tuple[float, ...]
        Coefficients (a0, a1, a2, ...).
    unit_in : str
        Unite attendue en entree (ex. "m/s").
    unit_out : str
        Unite de sortie ("-").

    Notes
    -----
    - eta(v) = a0 + a1*v + a2*v^2 + ...
    - Sortie adimensionnelle pour autowire dans VariableEtaConverter.
    - Le bornage eventuel de eta(t) est realise lors de l'attachement au
      convertisseur, pas dans cet adapter.
    """
    id: str
    source: str
    unit_in: str     # ex. 'm/s'
    unit_out: str    # nd, ex. '-', pour satisfaire le schéma de base pydantic
    coeffs: tuple[float, ...]

    def apply(self, series: FArray, unit: str) -> tuple[FArray, str]:
        # 1) vitesse -> unit_in
        v, _ = convert_unit(series, unit_in=unit, unit_out=self.unit_in, quantity="speed")
        # TODO: documenter dans les donnees projet l'origine, l'unite d'entree
        # et le domaine de validite des coefficients eta(v).
        # 2) polynôme
        eta_profile = np.zeros_like(v, dtype=np.float64)
        p = np.ones_like(v, dtype=np.float64)
        for a in self.coeffs:
            eta_profile += a * p
            p *= v
        return eta_profile, "-"

@register("speed_to_eta_poly", SpeedToEtaPolyParams)
def _build_speed_to_eta_poly(
        id: str, source: str, unit_in: str, unit_out: str, p: SpeedToEtaPolyParams,
) -> AdapterABC:
    return SpeedToEtaPoly(
        id=id, source=source, unit_in=unit_in, unit_out=unit_out,
        coeffs=tuple(p.coeffs)
    )


# ============================================================
# ---- Impl 5 — puissance -> puissance , poly (mono-entrée)
# ============================================================

class PowerToPowerPolyParams(AdapterParams):
    coeffs: list[float] = Field(min_length=1)
    clip_min: float | None = 0.0  # par défaut on clippe à 0

@dataclass
class PowerToPowerPolyAdapter(AdapterABC):
    """
    Adapter puissance -> puissance via polynome.

    Cet adapter sert a transformer un profil de puissance deja disponible en un
    autre profil de puissance. Il peut etre utilise pour appliquer une correction
    empirique, changer d'echelle ou fournir un passage explicite entre un profil
    et le solveur lorsque l'interface impose de passer par un adapter.

    Parameters
    ----------
    coeffs : tuple[float, ...]
        Coefficients (a0, a1, a2, ...).
    unit_in : str
        Unite attendue en entree (ex. "kW").
    unit_out : str
        Unite de sortie (ex. "W").
    clip_min : float | None
        Valeur minimale (None pour ne pas clipper).

    Notes
    -----
    - P(p) = a0 + a1*p + a2*p^2 + ...
    - Conversion d'unites automatique vers unit_in.
    - Les coefficients sont appliques a la puissance exprimee dans `unit_in`.
    - La sortie du polynome est interpretee comme une puissance en W avant
      conversion vers `unit_out`.
    - Pour un simple passage direct, utiliser `unit_in="W"`, `unit_out="W"` et
      `coeffs=(0.0, 1.0)`.
    """
    id: str
    source: str
    unit_in: str    # ex 'kW'
    unit_out: str   # ex 'W'
    coeffs: tuple[float, ...]  # a0, a1, ...
    clip_min: float | None

    def apply(self, series: FArray, unit: str) -> tuple[FArray, str]:
        # 1) puissance -> unit_in
        s, _ = convert_unit(series, unit_in=unit, unit_out=self.unit_in, quantity="power")
        # 2) poly
        out = np.zeros_like(s, dtype=np.float64)
        p = np.ones_like(s, dtype=np.float64)
        for a in self.coeffs:
            out += a * p
            p *= s
        # 3) clip
        if self.clip_min is not None:
            out = np.clip(out, float(self.clip_min), None)
        # 4) puissance native -> unit_out déclarée
        out, uo = convert_unit(out, unit_in="W", unit_out=self.unit_out, quantity="power")
        return out, uo

@register("power_to_power_poly", PowerToPowerPolyParams)
def _build_power_to_power_poly(
        id: str, source: str, unit_in: str, unit_out: str, p: PowerToPowerPolyParams
) -> AdapterABC:
    return PowerToPowerPolyAdapter(
        id=id, source=source, unit_in=unit_in, unit_out=unit_out,
        coeffs=tuple(p.coeffs), clip_min=p.clip_min
    )
