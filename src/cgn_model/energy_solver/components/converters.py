# cgn_model/energy_solver/components/converters.py

"""
Registry des convertisseurs + contrat de base (ConverterABC).

Ce module est le SEUL endroit à modifier quand vous ajoutez un nouveau
type de convertisseur. Le reste du système (config, solver_dag) n’a pas
besoin d’être changé.

# Rôle
- Fournit le contrat nominal `ConverterABC` (méthodes `forward`/`inverse`).
- Expose un **registre** de convertisseurs (clé `kind` -> (ParamsModel, builder)).
- Valide les paramètres spécifiques via un **modèle Pydantic** par type.
- Construit une instance concrète via `build_converter_from_cfg(c)` à partir
  d’un élément `ConverterCfg` (id, from_bus, to_bus, kind, params).

# Flux de configuration (YAML)
Un convertisseur se décrit ainsi :

    converters:
      - id: "genset"
        from_bus: "Chemical:fuel"
        to_bus:   "Electrical:main"
        kind: "constant_eta"
        params:
          eta: 0.45

**Compat retro** : si `kind` est omis mais qu’un `eta` top-level est présent,
`solver_dag._parse_cfg` migre vers :
    kind="constant_eta", params={"eta": ...}
et émet un `warnings.warn`.

# Comment AJOUTER un nouveau type
1) **Définir** un modèle de paramètres (Pydantic) :
    class MyParams(ConverterParams):
        alpha: float = Field(gt=0)

2) **Implémenter** la classe concrète :
    @dataclass
    class MyConverter(ConverterABC):
        id: str
        from_bus: str
        to_bus: str
        alpha: float
        p_in_w:  FArray | None = field(default=None, init=False)
        p_out_w: FArray | None = field(default=None, init=False)
        def forward(self, p_in_w: FArray) -> FArray:
            # ... votre logique ...
            return p_in_w * self.alpha
        def inverse(self, p_out_w: FArray) -> FArray:
            # ... votre logique inverse ...
            return p_out_w / self.alpha

3) **Enregistrer** le type avec un builder :
    @register("my_kind", MyParams)
    def build_my_kind(id: str, from_bus: str, to_bus: str, params: MyParams) -> ConverterABC:
        return MyConverter(id=id, from_bus=from_bus, to_bus=to_bus, alpha=params.alpha)

C’est tout. Le `SolverDAG` sait déjà construire vos convertisseurs via
`build_converter_from_cfg`, en fonction de `kind`.

# API exposée
- class ConverterABC(ABC):
    - `forward(p_in_w: FArray) -> FArray` : applique la conversion du bus `from_bus`
      vers `to_bus`. **Convention** : `p_in_w` représente un retrait sur `from_bus`,
      `p_out_w` (résultat) une injection sur `to_bus`. Unités en watts (W), shape
      vectorielle autorisée (broadcast NumPy).
    - `inverse(p_out_w: FArray) -> FArray` : conversion inverse (utile pour le mode
      solveur "inverse").

- class ConverterParams(BaseModel):
    - Base pour les modèles Pydantic de paramètres spécifiques. `extra="forbid"`
      empêche les fautes de frappe.

- decorator `@register(kind: str, params_model: type[ConverterParams])`
    - Associe un identifiant de type (ex. "constant_eta") à (ParamsModel, builder).
    - Le builder reçoit `(id, from_bus, to_bus, params)` et doit retourner un `ConverterABC`.

- function `build_converter_from_cfg(c: ConverterCfg) -> ConverterABC`
    - Valide `c.params` avec le `ParamsModel` du `kind`, instancie le convertisseur
      via le builder enregistré.
    - Lève `NotImplementedError` si `kind` est inconnu (liste des kinds dispo dans le message).

# Bonnes pratiques
- Gardez vos builders **purs** (pas d’effets de bord).
- Validez toute contrainte de domaine dans le `ParamsModel` (ex. bornes, tailles).
- Pour forcer un dtype homogène, vous pouvez convertir en `np.asarray(x, dtype=np.float64)`
  dans vos implémentations.
- Si vous ajoutez plusieurs convertisseurs, préférez des noms `kind` explicites
  et documentez les champs attendus dans `params`.

# Types
- `FArray` = `NDArray[np.floating]` (profil(s) vectoriels). Si vous voulez imposer
  float64, remplacez par `NDArray[np.float64]`.
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
    p_in_w : retrait appliqué sur from_bus
    p_out_w : injection effectuée sur to_bus
    """
    id: str
    from_bus: str
    to_bus: str
    
    @abstractmethod
    def forward(self, p_in_w: FArray) -> FArray: ...
    @abstractmethod
    def inverse(self, p_out_w: FArray) -> FArray: ...

# ---- registre
class ConverterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

RegistryEntry = tuple[Type[ConverterParams], Callable[[str, str, str, ConverterParams], ConverterABC]]
REGISTRY: dict[str, RegistryEntry] = {}

def register(kind: str, params_model: Type[ConverterParams]):
    def deco(builder: Callable[[str, str, str, ConverterParams], ConverterABC]):
        REGISTRY[kind] = (params_model, builder)
        return builder
    return deco

# ---- builder générique (utilisé par SolverDAG)
def build_converter_from_cfg(c) -> ConverterABC:
    """
    c: config.ConverterCfg (id, from_bus, to_bus, kind, params)
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
class ConstantEtaConverter(ConverterABC):
    """
    p_in_w : retrait appliqué sur from_bus
    p_out_w : injection effectuée sur to_bus
    """
    id: str
    from_bus: str
    to_bus: str
    eta: float
    p_in_w:  FArray | None = field(default=None, init=False)
    p_out_w: FArray | None = field(default=None, init=False)
    def forward(self, p_in_w: FArray) -> FArray:  return p_in_w * self.eta
    def inverse(self, p_out_w: FArray) -> FArray: return p_out_w / self.eta

@register("constant_eta", ConstantEtaParams)
def build_constant_eta(id: str, from_bus: str, to_bus: str, params: ConstantEtaParams
) -> ConverterABC:
    return ConstantEtaConverter(
        id=id, from_bus=from_bus, to_bus=to_bus, eta=params.eta
    )

# ------------------------------------------------------------
