import yaml

from cgn_model.vessel_model import Vessel


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
    unit: "m/s"
    source: "cgn_croisieres/all"
    select:
      by: "cruise"
      cruise_name: "Lavaux - Haut-Lac - Grand-Lac"

adapters:
    # 1) vitesse -> force (polynôme)
  - id: "resistance_from_speed"
    kind: "speed_to_force_poly"
    source: "speed"
    unit_in: "m/s"
    unit_out: "N"
    params:
      coeffs: [-208.7, 1902.9, 530.5, 95.1]
    
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
      unit_out: "W"

inputs:
  - id: "shaft_demand"
    bus: "shaft"
    source: "shaft_power_from_Fv"

  - id: "navops"
    bus: "elec_power"
    source: "hotel_load"

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
mapping = vessel.build_solver_inputs()
for k, (bus, arr) in mapping.items():
    print(k, "->", bus, "| len:", len(arr), "| first:", round(float(arr[0]),2), "| max:", round(max(arr),2))
