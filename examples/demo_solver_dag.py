# demo_solver_dag.py

import numpy as np
import yaml
import matplotlib.pyplot as plt

from pint import UnitRegistry

from cgn_model.energy_solver import SolverDAG, prepare_state, run_vector

def plot_state(solver: SolverDAG, t) -> None:
    
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
    
    pci_fuel = 10 # (kWh / litre)
    p_chem_net = solver.buses['Chemical:fuel'].net_w
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


def speed_to_shaft_power(v_t, coefs):
    from numpy.polynomial.polynomial import polyval
    shaft_force_resistance = polyval(v_t, coefs)
    shaft_power = shaft_force_resistance * v_t
    shaft_power_demand = np.clip(shaft_power, 0, None)
    return shaft_power_demand

def read_yaml(file):
    with open(file) as stream:
        try:
            cfg = yaml.safe_load(stream)
            return cfg
        except yaml.YAMLError as exc:
            print(exc)
        

# Paramètres vecteurs
t_tot = 3600 # (s)
dt = 1       # (s)
v_max = 7    # (m/s)
t_acc = 175  # (s)
r_aux_prop = 0.2/0.8 # (%), rapport puissance aux/prop

ms_coefs = np.array([-208.7215, 1902.932496, 530.5380768, 95.09285952]) # C0, C1, C2, C3

# Calculs
t = np.arange(0, t_tot, dt)
v_t = np.concatenate((
    np.linspace(0, v_max, t_acc),
    np.ones(t_tot - 2*t_acc)*v_max,
    np.linspace(v_max, 0, t_acc)
    
))

p_t = -1 * speed_to_shaft_power(v_t, ms_coefs)
nav_t = np.ones(t_tot)*np.mean(p_t) *r_aux_prop

# profils (négatifs = demandes)
profiles = {
    "shaft_demand": p_t,   # demande sur le bus mécanique
    "navops":       nav_t,   # demande sur le bus électrique
}

# Config
cfg_txt = """
vessel:
  name: "Vevey"
  type: "DE"
  
profil_vitesse:
    coefs:
      [0.2, 0.3, -2, ..]

solver:
  mode: "inverse"

buses:
  - {id: "Mechanical:shaft", carrier: "Mechanical"}
  - {id: "Electrical:main",  carrier: "Electrical"}
  - {id: "Chemical:fuel",    carrier: "Chemical"}

inputs:
  - {id: "shaft_demand", bus: "Mechanical:shaft"}
  - {id: "navops",       bus: "Electrical:main"}

converters:
  - id: "genset"
    from_bus: "Chemical:fuel"
    to_bus:   "Electrical:main"
    kind: "constant_eta"
    params:
      eta:  0.38
  - id: "motor"
    from_bus: "Electrical:main"
    to_bus:   "Mechanical:shaft"
    eta:  0.9    # Fallback sur "constant_eta" si "kind" non renseigé et "eta" présent au top-level
"""

cfg = read_yaml("config_demo_solver_dag.yaml")
# cfg = yaml.safe_load(cfg_txt)

solver = SolverDAG.from_yaml(cfg)

# solver.draw_dag()

prepare_state(solver, profiles)
run_vector(solver)

# quick sanity prints
print("net_W Mechanical:", solver.buses["Mechanical:shaft"].net_w[:3])
print("net_W Electrical:", solver.buses["Electrical:main"].net_w[:3])
print("net_W Chemical:  ", solver.buses["Chemical:fuel"].net_w[:3])
print("motor p_in / p_out:", solver.converters["motor"].p_in_w[:3], solver.converters["motor"].p_out_w[:3])
print("genset p_in / p_out:", solver.converters["genset"].p_in_w[:3], solver.converters["genset"].p_out_w[:3])


plot_state(solver, t)



