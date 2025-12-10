import numpy as np
import matplotlib.pyplot as plt
import yaml

from cgn_model.vessel_model import Vessel
from cgn_model.energy_solver import run_vector


def read_yaml(file):
    with open(file) as stream:
        try:
            cfg = yaml.safe_load(stream)
            return cfg
        except yaml.YAMLError as exc:
            print(exc)
    
# === Création de la classe Vessel via la config ===
cfg_file = "config_copil_251212.yaml"

cfg = read_yaml(cfg_file)
vessel = Vessel.from_yaml(cfg)

# === Calcul et connextion des inputs au solveur ===
mapping = vessel.apply_inputs_to_solver(verbose=True)

# === Execution du calcul par le solveur ===
run_vector(vessel.solver)

