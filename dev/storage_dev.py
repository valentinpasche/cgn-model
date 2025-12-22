
cfg_txt = """
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
    
# === Test de base ===

# 1) Construire le Vessel
from cgn_model.vessel_model import Vessel
vessel = Vessel.from_yaml(cfg_txt)

# 2) Câbler les inputs (prépare les états du solver et fige N)
vessel.build_solver(verbose=True)

# 3) Lancer la résolution
from cgn_model.energy_solver import run_vector
run_vector(vessel.solver)

# 4) Calculer les stockages
stor = vessel.tally_storages()

# 5) Accès résultats
res = stor["fuel_tank"]
res.summary
t = vessel.t  # vecteur temps [s] si besoin de tracer res.energy_kWh_cum

df_res = res.to_dataframe()
dct = res.summary_dict()

df_full = vessel.results_dataframe()

df_perso = vessel.results_dataframe(["time", "navops"])


