# Script demo détaillé, 05.06.2026 - CGN model v1.2

from pathlib import Path

import matplotlib.pyplot as plt

from cgn_model import Vessel
from cgn_model.energy_solver import run_vector

# ---- 1) Importer la configuration YAML
example_dir = Path(__file__).resolve().parent
yaml_text = (example_dir / "config.yaml").read_text(encoding="utf-8")

# ---- 2) Construire le Vessel
vessel = Vessel.from_yaml(yaml_text)

# ---- 3) Câbler les inputs (prépare les états du solver et fige N)
vessel.build_solver(verbose=True)

# ---- 4) Lancer la résolution
run_vector(vessel.solver)

# ---- 5) Calculer les stockages
vessel.tally_storages()

# ---- 6) Accès aux résultats
df = vessel.results_dataframe()

# ---- 7) Affichage des résultats
time = df["time_s"]
speed = df["profile_speed_m_per_s"]
shaft_power = df["input_shaft_demand_W"]
fuel_level = df["storage_fuel_tank_v_stock_l"]

# -------------------------- #

fig, ax1 = plt.subplots(figsize=[9, 6])
plt.title("Modele CGN - Resultats - Exemple v1.2")

color1 = 'blue'
ax1.set_xlabel('time (s)')
ax1.set_ylabel('Speed (m/s)', color=color1)
ax1.tick_params(axis='y', labelcolor=color1)
ax1.plot(time, speed, color=color1)

color2 = 'green'
ax2 = ax1.twinx()
ax2.set_ylabel('Shaft power (W)', color=color2)
ax2.tick_params(axis='y', labelcolor=color2)
ax2.plot(time, shaft_power, color=color2)

color3 = 'orange'
ax3 = ax1.twinx()
ax3.set_ylabel('Fuel level (liters)', color=color3)
ax3.tick_params(axis='y', labelcolor=color3)
ax3.plot(time, fuel_level, color=color3)
ax3.spines.right.set_position(("axes", 1.1))

fig.tight_layout()
plt.show()


# ---- 8) Sauvegarde des résultats
results_path = example_dir / "results.csv"
cols = [
    "time_s",
    "profile_speed_m_per_s",
    "converter_motor_out_W",
    "converter_genset_out_W",
    "storage_fuel_tank_e_cum_J",
    "storage_fuel_tank_v_stock_l",
]
df_export = df[cols].copy()

# df_export.to_csv(results_path, sep=";", index=False)
