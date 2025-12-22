# Script demo, 22.12.2025 - CGN model V1

import yaml

# ---- 1) Importer la configuration YAML
with open("config_v1.yaml", "r") as f:
    cfg = yaml.safe_load(f)

# ---- 2) Construire le Vessel
from cgn_model.vessel_model import Vessel
vessel = Vessel.from_yaml(cfg)

# ---- 3) Câbler les inputs (prépare les états du solver et fige N)
vessel.build_solver(verbose=True)

# ---- 4) Lancer la résolution
from cgn_model.energy_solver import run_vector
run_vector(vessel.solver)

# ---- 5) Calculer les stockages
vessel.tally_storages()

# ---- 6) Accès aux résultats
df = vessel.results_dataframe()
df_meta = df.attrs["units"] # ["colonnes" : "unites"]

# Pas encore dans le modele - Calcul du volume de carburant (mazout)
pci = 35.28e9 # J/m3 (9.8 kWh/l)
df["fuel_cum_m3"] = df["fuel_tank_e_cum_J"] / pci

# ---- 7) Affichaige des résultats
import matplotlib.pyplot as plt

time = df["time_s"]
speed = df["speed_m_per_s"]
shaft_power = df["shaft_demand_W"]
fuel_power = df["fuel_tank_e_cum_J"]
fuel_consome = df["fuel_cum_m3"]

# -------------------------- #

fig, ax1 = plt.subplots(figsize=[9, 6])
plt.title("Modele CGN - Resultats")

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

# color3 = 'orange'
# ax3 = ax1.twinx()
# ax3.set_ylabel('Power cumul (J)', color=color3)
# ax3.tick_params(axis='y', labelcolor=color3)
# ax3.plot(time, fuel_power, color=color3)
# ax3.spines.right.set_position(("axes", 1.1))

color4 = 'red'
ax4 = ax1.twinx()
ax4.set_ylabel('Fuel consommé (m^3)', color=color4)
ax4.tick_params(axis='y', labelcolor=color4)
ax4.plot(time, fuel_consome, color=color4)
ax4.spines.right.set_position(("axes", 1.2))

fig.tight_layout()
plt.show()


# ---- 8) Sauvegarde des résultats
csv_name = "demo_v1_results.csv"
cols = [
    "time_s",
    "speed_m_per_s",
    "hotel_load_W",
    "motor_out_W",
    "genset_out_W",
    "fuel_tank_p_W",
    "fuel_tank_e_cum_J",
    "fuel_cum_m3",
]
df_export = df[cols].copy()

# df_export.to_csv(csv_name, sep=";", index=False)
