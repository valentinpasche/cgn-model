
yaml_str = """
vessel:
  name: "Vevey"
  vessel_type: "DE"

simulation:
  dt: 1.0  # [s]

profiles:
  - id: "hotel_load"
    kind: "constant"
    unit: "W"
    value: 100e3

  - id: "speed"
    kind: "nav_speed"
    unit: "m/s"
    source: "cgn_croisieres/all"
    select:
      by: "cruise"                                # "cruise" | "course" | "leg"
      cruise_name: "Lavaux - Haut-Lac"                       # si by="cruise"
      course_no: 982                                         # si by="course"
      leg: { from_port: "Rolle", to_port: "Yvoire" }         # si by="leg"
    params:
      acc: 0.05            # [m/s²]
      dec: 0.05            # [m/s²]
      v_croisiere: 7     # [m/s]
      allow_delay: true

adapters:
  - id: "shaft_power_from_speed"
    kind: "speed_to_power_poly"
    source: "speed"
    unit_in: "m/s"
    unit_out: "W"
    params:
      coeffs: [0.0, -209.0, 1904.4, 531.36, 93.312]  # coefficients "m/s" to  "W"

  - id: "eta_from_speed"
    kind: "speed_to_eta_poly"
    source: "speed"
    unit_in: "m/s"
    unit_out: "-"
    params:
      coeffs: [0.11138307, 0.03562645, 0.00436722, -0.00056904]  # coefficients "m/s" to η genset

inputs:
  - id: "shaft_demand"
    bus: "shaft"
    source: "shaft_power_from_speed"
    sign: "consume"

  - id: "navops"
    bus: "elec_power"
    source: "hotel_load"
    sign: "consume"

solver:
  mode: "inverse"

buses:
  - id: "shaft"
    carrier: "Mechanical"

  - id: "elec_power"
    carrier: "Electrical"

  - id: "fuel"
    carrier: "Chemical"

converters:
  - id: "motor"
    from_bus: "elec_power"
    to_bus:   "shaft"
    kind: "constant_eta"
    params:
      eta: 0.9   # [-]

  - id: "genset"
    from_bus: "fuel"
    to_bus:   "elec_power"
    kind: "variable_eta"
    params:
      eta_default: 0.38   # [-]
      eta_source: "eta_from_speed"

storages:
  - id: "fuel_tank"
    bus: "fuel"           # le bus chimique du DAG
    vecteur: "diesel"
"""




# ---- 1) Pipeline Vessel complet, orchestrateur global
from cgn_model.vessel_model import Vessel

vessel = Vessel.from_yaml(yaml_str)
vessel.run()
df = vessel.results_dataframe()



# ---- 2) Affichaige des résultats
import matplotlib.pyplot as plt

fig, ax1 = plt.subplots(figsize=[9, 6])
plt.title("Modele CGN - Resultats")

color1 = 'blue'
ax1.set_xlabel('time (s)')
ax1.set_ylabel('Speed (m/s)', color=color1)
ax1.tick_params(axis='y', labelcolor=color1)
ax1.plot(df["time_s"], df["profile_speed_m_per_s"], color=color1)

color2 = 'green'
ax2 = ax1.twinx()
ax2.set_ylabel('Shaft power (W)', color=color2)
ax2.tick_params(axis='y', labelcolor=color2)
ax2.plot(df["time_s"], df["input_shaft_demand_W"], color=color2)

color3 = 'orange'
ax3 = ax1.twinx()
ax3.set_ylabel('Power net (W)', color=color3)
ax3.tick_params(axis='y', labelcolor=color3)
ax3.plot(df["time_s"], df["storage_fuel_tank_p_W"], color=color3)
ax3.spines.right.set_position(("axes", 1.1))

color4 = 'red'
ax4 = ax1.twinx()
ax4.set_ylabel('Power cumul (J)', color=color4)
ax4.tick_params(axis='y', labelcolor=color4)
ax4.plot(df["time_s"], df["storage_fuel_tank_e_cum_J"], color=color4)
ax4.spines.right.set_position(("axes", 1.2))

fig.tight_layout()
plt.show()


