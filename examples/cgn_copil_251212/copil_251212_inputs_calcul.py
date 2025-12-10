import numpy as np
import matplotlib.pyplot as plt
import yaml
import pandas as pd

from pint import UnitRegistry

from cgn_model.vessel_model import Vessel
from cgn_model.energy_solver import run_vector


def plot_state(solver, dt: float) -> None:
    
    key_0 = list(solver.buses.keys())[0]
    N = len(solver.buses[key_0].net_w)
    t = np.arange(0, N*dt, dt)
    
    fig, ax = plt.subplots()
    
    for conv_id, data in solver.converters.items():
        p = data.p_out_w
        ax.plot(t, p, label=conv_id)
        
    for input_id, data in solver.inputs.items():
        ax.plot(t, data.profile, label=input_id)
    
    ax.set(xlabel='time (s)', ylabel='Power (W)',
           title='Profil de puissance, "p_out_w" convertisseurs et inputs')
    ax.grid()
    
    pci_fuel = 9.8 # (kWh / litre)
    p_chem_net = solver.buses['fuel'].net_w
    conso_fuel = bus_chem_power_to_stock_fuel(p_chem_net, pci_fuel)
    
    ax2 = ax.twinx()
    ax2.plot(t, conso_fuel, label="cons_fuel", ls='-.', lw=3, color="black")
    ax2.set_ylabel("Volume de fuel (m^3)")
    
    fig.legend()
    plt.show()
    
    return None

def bus_chem_power_to_stock_fuel(p_chem_net, pci_fuel):
    ureg = UnitRegistry()
    pci_fuel = pci_fuel * (ureg.kWh / ureg.liter) # (kWh / litre)
    pci = pci_fuel.to("W*s/m^3").magnitude # (Ws / m^3)
    tot_fuel = np.cumsum(p_chem_net / pci)
    return tot_fuel

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


plot_state(vessel.solver, vessel.dt)


dt = vessel.dt
vitesse = vessel.signals["speed"][0]
puissance_arbre = vessel.signals["shaft_power_from_speed"][0]
temps = dt*len(vitesse)

pci_fuel = 9.8 # (kWh / litre)
fuel_net_w = vessel.solver.buses["fuel"].net_w
fuel_cumule = bus_chem_power_to_stock_fuel(fuel_net_w, pci_fuel)

data = {
    "temps (s)": temps,
    "speed (m/s)": vitesse,
    "power_shaft (W)": puissance_arbre,
    "fuel_cumul (m^3)": fuel_cumule,
}

df = pd.DataFrame(data)

df.to_csv("exemple_copil_251212.csv", sep=";", decimal=".")
# def export_valeurs(vessel) -> pd.DataFrame:
    

    
    
#     return df

