# cgn_model/energy_solver/components/converters.py

"""
Convertisseurs energetiques du `SolverDAG` et registre de construction.

Role du module
--------------
Ce module contient le contrat runtime des convertisseurs et le registre qui
associe un `kind` YAML a une implementation Python. Un convertisseur relie un
bus `from_bus` a un bus `to_bus` et fournit deux operations vectorielles :

- `forward(p_in_w)` : calcule la puissance de sortie a partir d'une puissance
  prelevee sur `from_bus`;
- `inverse(p_out_w)` : calcule la puissance d'entree necessaire pour obtenir
  une puissance cible sur `to_bus`.

Les puissances sont exprimees en watts [W]. La convention de bilan utilisee par
`run_dag` est : `p_in_w` est un retrait sur le bus amont, `p_out_w` est une
injection sur le bus aval.

Le sens `from_bus` -> `to_bus` correspond au sens physique nominal de la
conversion energetique. Par exemple, un moteur thermique preleve une puissance
chimique sur un bus `Chemical:*` (`from_bus`) pour fournir une puissance
mecanique sur un bus `Mechanical:*` (`to_bus`). Dans le DAG, les `carrier`
restent des metadonnees descriptives; les bilans internes sont bloques en W.

Convertisseurs fournis
----------------------
- `constant_eta` : rendement constant `eta`, avec `0 < eta <= 1`.
- `variable_eta` : rendement temporel optionnel `eta_profile`; si aucun profil
  n'est attache, le convertisseur utilise `eta_default`. Le champ `eta_source`
  reference le signal adimensionnel qui peut etre attache par `Vessel`.

Flux YAML
---------
Un convertisseur se declare dans la section `converters` :

    converters:
      - id: "genset"
        from_bus: "Chemical:fuel"
        to_bus: "Electrical:main"
        kind: "constant_eta"
        params:
          eta: 0.45

Compatibilite historique : `solver_dag._parse_cfg` migre encore un champ `eta`
top-level vers `kind="constant_eta"` et `params={"eta": ...}`.

Registre et extension
---------------------
Le registre interne `REGISTRY` mappe `kind -> (ParamsModel, builder)`.
`build_converter_from_cfg(c)` lit `c.kind`, valide `c.params` avec le modele
Pydantic associe, puis appelle le builder.

Pour ajouter un convertisseur dans le coeur solver :

1. definir un modele de parametres derive de `ConverterParams`;
2. implementer une classe qui respecte `ConverterABC`;
3. enregistrer un builder avec `@register("nouveau_kind", ParamsModel)`.

Si ce nouveau convertisseur doit aussi etre cree depuis l'interface web ou
documente pour les utilisateurs YAML, il faudra mettre a jour les couches UI,
les exemples et la documentation externe correspondants.

Bonnes pratiques
----------------
- Garder les builders sans effet de bord.
- Valider les bornes physiques dans le modele Pydantic.
- Documenter les unites et le domaine de validite des parametres.
- Conserver des noms de `kind` explicites et stables.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Callable, Type
from pydantic import BaseModel, Field, ConfigDict

import numpy as np
from numpy.typing import NDArray

type FArray = NDArray[np.floating]

__all__ = ["ConverterABC", "build_converter_from_cfg"]

# ============================================================
# ----            Base + Registre d’adapters
# ============================================================

# ---- base ABC: Contrat nominal (impl imposée)
class ConverterABC(ABC):
    """
    Contrat de convertisseur pour le SolverDAG.
    Un convertisseur relie un bus from_bus a un bus to_bus et fournit
    deux fonctions :
    - forward(p_in_w) : convertit une puissance entrante vers la sortie
    - inverse(p_out_w) : calcule l'entree requise pour une sortie cible

    Parameters
    ----------
    p_in_w : FArray
        Puissance retiree de from_bus (W).
    p_out_w : FArray
        Puissance injectee sur to_bus (W).
    
    Notes
    -----
    - Les unites du solver sont en W (SI) et les profils sont 1D.

    Examples
    --------
    Convertisseur simple a rendement constant :
    >>> from dataclasses import dataclass
    >>> @dataclass
    ... class MyConverter(ConverterABC):
    ...     id: str
    ...     from_bus: str
    ...     to_bus: str
    ...     eta: float
    ...     def forward(self, p_in_w):
    ...         return p_in_w * self.eta
    ...     def inverse(self, p_out_w):
    ...         return p_out_w / self.eta
    """
    id: str
    from_bus: str
    to_bus: str
    
    @abstractmethod
    def forward(self, p_in_w: FArray) -> FArray: ...
    @abstractmethod
    def inverse(self, p_out_w: FArray) -> FArray: ...

# --- petit mixin dataclass pour les logs communs ---
@dataclass
class LoggedConverter:
    p_in_w:  FArray | None = field(default=None, init=False)   # retrait from_bus
    p_out_w: FArray | None = field(default=None, init=False)   # injection to_bus

# ---- registre
class ConverterParams(BaseModel):
    """
    Base Pydantic pour les parametres de convertisseurs.

    Notes
    -----
    - extra="forbid" empeche les fautes de frappe dans le YAML.
    """
    model_config = ConfigDict(extra="forbid")

RegistryEntry = tuple[Type[ConverterParams], Callable[[str, str, str, ConverterParams], ConverterABC]]
REGISTRY: dict[str, RegistryEntry] = {}

def register(kind: str, params_model: Type[ConverterParams]):
    """
    Enregistre un convertisseur dans le registre global.

    Parameters
    ----------
    kind : str
        Identifiant du type de convertisseur (ex. "constant_eta").
    params_model : type[ConverterParams]
        Modele Pydantic pour valider les parametres.
    
    Returns
    -------
    callable
        Decorateur qui enregistre un builder.
    """
    def deco(builder: Callable[[str, str, str, ConverterParams], ConverterABC]):
        REGISTRY[kind] = (params_model, builder)
        return builder
    return deco

# ---- builder générique (utilisé par SolverDAG)
def build_converter_from_cfg(c) -> ConverterABC:
    """
    Construit un convertisseur a partir d'une config validee.

    Parameters
    ----------
    c : ConverterCfg
        Configuration (id, from_bus, to_bus, kind, params).
    
    Returns
    -------
    ConverterABC
        Instance de convertisseur.
    
    Raises
    ------
    NotImplementedError
        Si kind n'est pas enregistre.
    """
    try:
        ParamsModel, builder = REGISTRY[c.kind]
    except KeyError:
        avail = ", ".join(sorted(REGISTRY.keys()))
        raise NotImplementedError(f"Kind inconnu: {c.kind!r}. Kinds dispo: {avail}")
    params = ParamsModel.model_validate(c.params or {})
    return builder(c.id, c.from_bus, c.to_bus, params)

# ============================================================
# ----    Impl 1 - Convertisseur à rendement constant
# ============================================================

class ConstantEtaParams(ConverterParams):
    eta: float = Field(gt=0, le=1, allow_inf_nan=False)

@dataclass
class ConstantEtaConverter(LoggedConverter, ConverterABC):
    """
    Convertisseur a rendement constant.

    Parameters
    ----------
    id : str
        Identifiant du convertisseur.
    from_bus : str
        Bus en entree.
    to_bus : str
        Bus en sortie.
    eta : float
        Rendement constant (0 < eta <= 1).

    Attributes
    ----------
    p_in_w : FArray | None
        Profil d'entree (W), rempli par le solver.
    p_out_w : FArray | None
        Profil de sortie (W), rempli par le solver.

    Notes
    -----
    - forward(p_in_w) = p_in_w * eta
    - inverse(p_out_w) = p_out_w / eta
    """
    id: str
    from_bus: str
    to_bus: str
    eta: float
    # p_in_w / p_out_w hérités de LoggedConverter
    
    def forward(self, p_in_w: FArray) -> FArray:  return p_in_w * self.eta
    def inverse(self, p_out_w: FArray) -> FArray: return p_out_w / self.eta

@register("constant_eta", ConstantEtaParams)
def build_constant_eta(id: str, from_bus: str, to_bus: str, params: ConstantEtaParams
) -> ConverterABC:
    return ConstantEtaConverter(
        id=id, from_bus=from_bus, to_bus=to_bus, eta=params.eta
    )

# ============================================================
# ----    Impl 2 - Convertisseur à rendement variable
# ============================================================

class VariableEtaParams(ConverterParams):
    eta_default: float = Field(gt=0, le=1, allow_inf_nan=False)
    eta_source: str | None = None

@dataclass
class VariableEtaConverter(LoggedConverter, ConverterABC):
    """
    Convertisseur a rendement variable dans le temps.

    Parameters
    ----------
    id : str
        Identifiant du convertisseur.
    from_bus : str
        Bus en entree.
    to_bus : str
        Bus en sortie.
    eta : float
        Rendement par defaut (fallback).
    eta_source : str | None
        ID d'un profil eta(t) (optionnel, pour autowire).

    Attributes
    ----------
    eta_profile : FArray | None
        Profil eta(t) attache, sinon None.
    p_in_w : FArray | None
        Profil d'entree (W), rempli par le solver.
    p_out_w : FArray | None
        Profil de sortie (W), rempli par le solver.

    Notes
    -----
    - Si eta_profile est None -> fallback sur eta (eta_default).
    - Sinon forward/inverse utilisent eta_profile[t] (clip a [1e-6, 1]).
    """
    id: str
    from_bus: str
    to_bus: str
    eta: float # fallback constant (eta_default)
    eta_profile: FArray | None = field(default=None, init=False)
    eta_source: str | None = None
    _eta_warned: bool = field(default=False, init=False, repr=False)
    # p_in_w / p_out_w hérités de LoggedConverter

    def _eta_vec(self, N: int) -> FArray:
        if self.eta_profile is None:
            if not self._eta_warned:
                print("variable_eta: fallback sur eta_default (profil η non attaché).")
                self._eta_warned = True
            return np.full(N, float(self.eta), dtype=np.float64)
        if self.eta_profile.ndim != 1:
            raise ValueError("eta_profile doit être 1D")
        if self.eta_profile.shape[0] != N:
            raise ValueError(f"eta_profile taille {self.eta_profile.shape} ≠ {(N,)}")
        return np.clip(self.eta_profile, 1e-6, 1.0)  # garde-fou

    def forward(self, p_in_w: FArray) -> FArray:
        eta_t = self._eta_vec(len(p_in_w))
        return p_in_w * eta_t

    def inverse(self, p_out_w: FArray) -> FArray:
        eta_t = self._eta_vec(len(p_out_w))
        return p_out_w / eta_t

@register("variable_eta", VariableEtaParams)
def build_variable_eta(id: str, from_bus: str, to_bus: str, params: VariableEtaParams) -> ConverterABC:
    return VariableEtaConverter(
        id=id, from_bus=from_bus, to_bus=to_bus,
        eta=params.eta_default,
        eta_source=params.eta_source
    )







