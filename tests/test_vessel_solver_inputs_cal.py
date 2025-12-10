import yaml

from cgn_model.vessel_model import Vessel
from cgn_model.energy_solver import prepare_state, run_vector


cfg_txt = """
vessel:
  name: "Vevey"
  vessel_type: "DE"

simulation:
  dt: 1.0

profiles:
  # 1) Constante
  - id: "hotel_load"
    kind: "constant"
    unit: "W"
    value: 100000

  # 4) Vitesse issue de l’horaire (module navigation)
  - id: "speed"
    kind: "nav_speed"
    unit: "m/s"            # unité du profil produit
    source: "cgn_croisieres/all"     # dataset interne
    select:
      by: "cruise"         # "cruise" | "course" | "leg"
      cruise_name: "Lavaux - Haut-Lac - Grand-Lac"     # si by="cruise"
      course_no: 982                                   # si by="course"
      leg: { from_port: "Rolle", to_port: "Yvoire" }   # si by="leg"
    params:                 # MRUA
      acc: 0.06             # [m/s²]
      dec: 0.06             # [m/s²]
      v_croisiere: 7        # [m/s]
      allow_delay: true

adapters:
    # 1) vitesse -> force (polynôme)
  - id: "resistance_from_speed"
    kind: "speed_to_force_poly"
    source: "speed"
    unit_in: "m/s"
    unit_out: "N"
    params:
      coeffs: [-209.0, 1904.4, 531.36, 93.312] # coefs vitesse "m/s" to force "N"
    
    # 2) puissance = F * v (multi-entrées)
  - id: "shaft_power_from_Fv"
    kind: "force_and_speed_to_power"
    source: ""
    unit_in: ""
    unit_out: "W"
    params:
      force_source: "resistance_from_speed"
      speed_source: "speed"
      force_unit_in: "N"
      speed_unit_in: "m/s"

inputs:
  - id: "shaft_demand"
    bus: "shaft"
    source: "shaft_power_from_Fv"
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
  - id: "genset"
    from_bus: "fuel"
    to_bus:   "elec_power"
    kind: "constant_eta"
    params:
      eta: 0.38

  - id: "motor"
    from_bus: "elec_power"
    to_bus:   "shaft"
    kind: "constant_eta"
    params:
      eta: 0.9
"""
    
# # === Test de base de la création de la classe Vessel ===
cfg = yaml.safe_load(cfg_txt)

vessel = Vessel.from_yaml(cfg)
mapping = vessel.build_solver_inputs() # Signe du profil !!!
for k, (bus, arr) in mapping.items():
    print(k, "->", bus, "| len:", len(arr), "| first:", round(float(arr[0]),2), "| max:", round(max(arr),2))
    
# # === Test combiné avec la création du solveur ===
prepare_state(vessel.solver, mapping) # Accepter le paramètre Vessel en plus
run_vector(vessel.solver) # Accepter le paramètre Vessel en plus

