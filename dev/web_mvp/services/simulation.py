"""
Services de simulation relies au coeur `cgn-model`.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import yaml

from cgn_model.energy_solver import run_vector
from cgn_model.vessel_model import Vessel


@dataclass
class SimulationOutput:
    """
    Resultat de simulation pour la couche UI.
    """

    dataframe: pd.DataFrame
    columns: list[str]
    n_rows: int


def run_simulation_from_yaml(yaml_text: str) -> SimulationOutput:
    """
    Execute la chaine standard `Vessel -> solver -> results_dataframe`.
    """
    cfg = yaml.safe_load(yaml_text)
    vessel = Vessel.from_yaml(cfg)
    vessel.build_solver(verbose=False)
    run_vector(vessel.solver)
    vessel.tally_storages(require_inputs_applied=True, require_solver_run=False)
    df = vessel.results_dataframe()
    return SimulationOutput(
        dataframe=df,
        columns=list(df.columns),
        n_rows=len(df),
    )
