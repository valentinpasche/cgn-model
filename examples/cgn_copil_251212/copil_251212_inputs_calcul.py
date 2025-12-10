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
            
def bus_chem_power_to_stock_fuel(p_chem_net, pci_fuel):
    ureg = UnitRegistry()
    pci_fuel = pci_fuel * (ureg.kWh / ureg.liter) # (kWh / litre)
    pci = pci_fuel.to("W*s/m^3").magnitude # (Ws / m^3)
    tot_fuel = np.cumsum(p_chem_net / pci)
    return tot_fuel

def export_valeurs(vessel: Vessel, pci_kWh_litre: int) -> pd.DataFrame():
    
    dt = vessel.dt
    vitesse = vessel.signals["speed"][0]
    puissance_arbre = vessel.signals["shaft_power_from_speed"][0]
    temps = dt*len(vitesse)
    
    fuel_net_w = vessel.solver.buses["fuel"].net_w
    fuel_cumule = bus_chem_power_to_stock_fuel(fuel_net_w, pci_kWh_litre)
    
    data = {
        "temps (s)": temps,
        "speed (m/s)": vitesse,
        "power_shaft (W)": puissance_arbre,
        "fuel_cumul (m^3)": fuel_cumule,
    }
    
    return pd.DataFrame(data)




    

# === Création de la classe Vessel via la config ===
cfg_file = "config_copil_251212.yaml"

cfg = read_yaml(cfg_file)
vessel = Vessel.from_yaml(cfg)

# === Calcul et connextion des inputs au solveur ===
mapping = vessel.apply_inputs_to_solver(verbose=True)

# === Execution du calcul par le solveur ===
run_vector(vessel.solver)

# === Export des résultats, DataFrame ===
pci_kWh_litre = 9.8 # (kWh / litre)
df = export_valeurs(vessel, pci_kWh_litre)

# # === Sauvegarde des résultats, CSV ===
# file_csv_output = "values_copil_251212.csv"
# df.to_csv(file_csv_output, sep=";")

# === Graphique du solveur, positions définies ===
positions_noeuds = { # X  ,  Y (centre à 0)
   'shaft_demand': [-1.00, +1.00],
   'navops':       [+1.00, +1.00],
   'shaft':        [-0.50, +0.20],
   'elec_power':   [+0.50, -0.20],
   'fuel':         [+1.00, -1.00],
}
vessel.solver.draw_dag(pos=positions_noeuds)






