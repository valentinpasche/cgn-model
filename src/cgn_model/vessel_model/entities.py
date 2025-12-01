# cgn_model/vessel_model/entities.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

import numpy as np
from numpy.typing import NDArray

type FArray = NDArray[np.floating]


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

# Petites aides de type
type Profiles = Dict[str, Profile]
type Signals  = Dict[str, tuple[FArray, str]]  # id -> (array, unit)
