"""
Execution de simulation pour UI V2.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from cgn_model.energy_solver import run_vector
from cgn_model.vessel_model import Vessel


@dataclass
class SimulationOutput:
    dataframe: pd.DataFrame
    columns: list[str]
    n_rows: int


def run_simulation_from_cfg(cfg: dict) -> SimulationOutput:
    vessel = Vessel.from_yaml(cfg)
    vessel.build_solver(verbose=False)
    run_vector(vessel.solver)
    vessel.tally_storages(require_inputs_applied=True, require_solver_run=False)
    df = vessel.results_dataframe()
    return SimulationOutput(dataframe=df, columns=list(df.columns), n_rows=len(df))
