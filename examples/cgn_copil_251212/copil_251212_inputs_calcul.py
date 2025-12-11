import numpy as np
import yaml
import pandas as pd

from pint import UnitRegistry

from cgn_model.vessel_model import Vessel
from cgn_model.energy_solver import run_vector


def read_yaml(file: str):
    with open(file) as stream:
        try:
            cfg = yaml.safe_load(stream)
            return cfg
        except yaml.YAMLError as exc:
            print(exc)
            
def bus_chem_power_to_stock_fuel(p_chem_net_w: np.ndarray, pci_kwh_per_l: float, dt_s: float) -> np.ndarray:
    """
    p_chem_net_w : profil de puissance chimique nette [W] (signe conforme à ta convention)
    pci_kwh_per_l: pouvoir calorifique inférieur [kWh / litre]
    dt_s         : pas de temps [s]
    retour       : volume cumulé [m^3]
    """
    pci = (pci_kwh_per_l * (ureg.kWh / ureg.liter)).to("W*s/m^3").magnitude  # [Ws/m^3]
    # volume instantané [m^3] = (W * s) / (Ws/m^3)
    vol_inst_m3 = (p_chem_net_w * dt_s) / pci
    return np.cumsum(vol_inst_m3)

    

# === Création de la classe Vessel via la config ===
cfg_file = "config_copil_251212.yaml"

cfg = read_yaml(cfg_file)
vessel = Vessel.from_yaml(cfg)

# === Calcul et connextion des inputs au solveur ===
mapping = vessel.apply_inputs_to_solver(verbose=True)

# === Execution du calcul par le solveur ===
run_vector(vessel.solver)

# === Export des résultats, DataFrame ===
ureg = UnitRegistry()
pci_kWh_litre = 9.8 # (kWh / litre)

vitesse_ms = vessel.signals["speed"][0]
puissance_arbre_w = vessel.signals["shaft_power_from_speed"][0]
temps = np.arange(len(vitesse_ms)) * vessel.dt

fuel_net_w = vessel.solver.buses["fuel"].net_w
fuel_cumule_mc = bus_chem_power_to_stock_fuel(fuel_net_w, pci_kWh_litre, vessel.dt)
fuel_cumule_l = fuel_cumule_mc * -1000

data = {
    "temps (s)": temps,
    "speed (m/s)": vitesse_ms,
    "power_shaft (W)": puissance_arbre_w,
    "fuel_cumul (m^3)": fuel_cumule_mc,
    "fuel_consom_cumul (litre)": fuel_cumule_l,
}
df = pd.DataFrame(data)

# # === Sauvegarde des résultats, CSV ===
# file_csv_output = "values_copil_251212.csv"
# df.to_csv(file_csv_output, sep=";", index=False)

# === Graphique du solveur, positions définies ===
positions_noeuds = { # X  ,  Y (centre à 0)
   'shaft_demand': [-1.00, +1.00],
   'navops':       [+1.00, +1.00],
   'shaft':        [-0.50, +0.20],
   'elec_power':   [+0.50, -0.20],
   'fuel':         [+1.00, -1.00],
}
vessel.solver.draw_dag(pos=positions_noeuds)
