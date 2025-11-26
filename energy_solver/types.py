# energy_solver/types.py

from collections.abc import Mapping
from typing import Literal

import numpy as np
from numpy.typing import NDArray


type FArray = NDArray[np.floating]

type Mode = Literal["forward", "inverse"]

type BusId = str
type ConvId = str
type Edge = tuple[BusId, BusId]
type PlanItem = tuple[Edge, ConvId]
type Plan = list[PlanItem]

type Coord = tuple[float, float] | FArray
type Pos = Mapping[str, Coord]
