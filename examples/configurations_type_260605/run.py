"""Charge et execute les configurations types du modele CGN."""

from pathlib import Path

import pandas as pd

from cgn_model import Vessel


EXAMPLE_DIR = Path(__file__).resolve().parent

CONFIG_FILES = [
    "config_DE.yaml",
    "config_steam.yaml",
    "config_full_elec.yaml",
    "config_H2.yaml",
    "config_from_UI.yaml",
]


def run_config(
    config_file: str,
    *,
    draw_dag: bool = False,
) -> tuple[pd.DataFrame, Vessel]:
    """Execute une configuration et retourne ses resultats et son Vessel."""
    yaml_text = (EXAMPLE_DIR / config_file).read_text(encoding="utf-8")

    vessel = Vessel.from_yaml(yaml_text)
    vessel.run()

    if draw_dag:
        vessel.solver.draw_dag()

    return vessel.results_dataframe(), vessel


if __name__ == "__main__":
    for config_file in CONFIG_FILES:
        df, vessel = run_config(config_file)
        print(
            f"{config_file}: "
            f"vessel={vessel.name!r}, "
            f"rows={len(df)}, "
            f"columns={len(df.columns)}, "
            f"buses={len(vessel.solver.buses)}, "
            f"converters={len(vessel.solver.converters)}"
        )
