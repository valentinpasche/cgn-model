" Pour tester les paramètres de création des inputs dans le YAML. "

import yaml

from cgn_model.vessel_model import Vessel


cfg_txt = """
vessel:
  name: "Vevey"
  vessel_type: "DE"                   # la clé "type" est aussi acceptée

simulation:
  dt: 1.0        # [s] pas de discrétisation global

profiles:
  # 1) Constante (différentes syntaxes)
  - id: "hotel_load"
    kind: "constant"
    unit: "W"
    value: 8000            # float/int ou [8000] (len=1)

  # # 2) Série inline
  # - id: "speed"
  #   kind: "series"
  #   unit: "m/s"
  #   data: [3.0, 3.5, 4.2, 3.8]
  #   master: true

  # # 3) Depuis un fichier (csv)
  # - id: "speed"
  #   kind: "file"
  #   unit: "m/s"             # sera converti si besoin dans tes adapters
  #   file: "speed_vector_ms.csv" # relatif au projet, ou absolu
  #   column: "speed_ms"     # optionnel: nom de colonne

  # 4) Vitesse issue de l’horaire (module navigation)
  - id: "speed"
    kind: "nav_speed"
    unit: "m/s"            # unité du profil produit
    source: "cgn_croisieres/all"     # dataset interne
    select:
      by: "cruise"         # "cruise" | "course" | "leg"
      cruise_name: "Lavaux - Haut-Lac - Grand-Lac"     # si by="cruise"
      course_no: 106                                   # si by="course"
      leg: { from_port: "Rolle", to_port: "Yvoire" }   # si by="leg"
    params:                 # MRUA
      acc: 0.04             # [m/s²]
      dec: 0.04             # [m/s²]
      v_croisiere: 7        # [m/s]
      allow_delay: true
    master: true            # ← ce profil pilote la longueur N

adapters:
    # 1) vitesse -> force (polynôme)
  - id: "resistance_from_speed"
    kind: "speed_to_force_poly"
    source: "speed"
    unit_in: "m/s"                    # l’adapter attend m/s
    unit_out: "N"                     # et produit des Newton
    params:
      # coefs vitesse "m/s" to force "N", e.g. ([a0, a1, a2] -> P = a0 + a1*v + a2*v^2)
      coeffs: [-209.0, 1904.4, 531.36, 93.312]
    
    # 2) puissance = F * v (multi-entrées)
  - id: "shaft_power_from_Fv"
    kind: "force_and_speed_to_power"
    # NB: 'source' top-level est ignoré par cet adapter (il utilise 2 sources dans params)
    source: ""  # (juste pour satisfaire le schéma générique)
    unit_in: "" # idem
    unit_out: "W"
    params:
      force_source: "resistance_from_speed"
      speed_source: "speed"
      force_unit_in: "N"
      speed_unit_in: "m/s"
      unit_out: "W"
    
  #   # 3) vitesse -> puissance (polynôme)
  # - id: "shaft_power_from_speed"
  #   kind: "speed_to_power_poly"
  #   source: "speed"
  #   unit_in: "m/s"                    # l’adapter attend m/s
  #   unit_out: "W"                     # et produit des Watts
  #   params:
  #     # ici juste 1 degré de plus que la combinaison de 1) + 2)
  #     coeffs: [0.0, -209.0, 1904.4, 531.36, 93.312]

inputs:
  - id: "shaft_demand"
    bus: "shaft"
    source: "shaft_power_from_Fv"  # via l’adapter (clé ignorée par le solver, utilisé par Vessel)

  - id: "navops"
    bus: "elec_power"
    source: "hotel_load"              # direct: déjà en W

solver:
  mode: "inverse"

buses:
  - { id: "shaft", carrier: "Mechanical" }   # unit implicite "W"
  - { id: "elec_power",  carrier: "Electrical" }
  - { id: "fuel",    carrier: "Chemical" }

converters:
  - id: "genset"
    from_bus: "fuel"
    to_bus:   "elec_power"
    kind: "constant_eta"
    params: { eta: 0.38 }

  - id: "motor"
    from_bus: "elec_power"
    to_bus:   "shaft"
    kind: "constant_eta"
    params: { eta: 0.9 }
"""
    
# # === Test de base de la création de la classe Vessel ===

cfg = yaml.safe_load(cfg_txt)
vessel = Vessel.from_yaml(cfg)
mapping = vessel.build_solver_inputs()
for k, (bus, arr) in mapping.items():
    print(k, "->", bus, "| len:", len(arr), "| first:", float(arr[0]), "| max:", max(arr))
