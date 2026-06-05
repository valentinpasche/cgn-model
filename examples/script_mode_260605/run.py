# Script demo simple, 05.06.2026 - CGN model v1.2

from pathlib import Path

from cgn_model import Vessel

example_dir = Path(__file__).resolve().parent
yaml_text = (example_dir / "config.yaml").read_text(encoding="utf-8")

vessel = Vessel.from_yaml(yaml_text)
vessel.run()

df = vessel.results_dataframe()

# Export optionnel.
cols = [
    "time_s",
    "profile_speed_m_per_s",
    "converter_motor_out_W",
    "storage_fuel_tank_v_stock_l",
]
# df.to_csv(example_dir / "results.csv", sep=";", columns=cols, index=False)
