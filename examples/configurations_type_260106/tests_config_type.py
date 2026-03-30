# Script demo, configurations types

import yaml
from cgn_model.vessel_model import Vessel
from cgn_model.energy_solver import run_vector


def process(config_file, draw_dag=False):

    with open(config_file, "r") as f:
        cfg = yaml.safe_load(f)
    
    vessel = Vessel.from_yaml(cfg)
    vessel.build_solver(verbose=True)
    run_vector(vessel.solver)
    vessel.tally_storages()
    
    if draw_dag:
        vessel.solver.draw_dag()
    
    df = vessel.results_dataframe()
    df_meta = df.attrs["units"]
    
    return df, df_meta

# --------------------------- Demo ---------------------------
if __name__ == "__main__":
    
    pci_mazout = 35.28e9 # J/m3 (9.8 kWh/l)
    densite_energetique_h2 = 33.3 # kWh/kg
    j_to_kwh = 3.6e6 # J to kWh (3'600'000 = 1 kWh)
    
    # ---- 1) Diesel-Electrique
    df_de, units_de = process("config_DE.yaml", draw_dag=False)
    # df_de["fuel_cum_m3"] = df_de["fuel_tank_e_cum_J"] / pci_mazout
    
    # ---- 2) Vapeur
    # df_steam, units_steam = process("config_steam.yaml", draw_dag=False)
    # df_steam["fuel_cum_m3"] = df_steam["fuel_tank_e_cum_J"] / pci_mazout
    
    # ---- 3) Full-electrique
    # df_full_elec, units_full_elec = process("config_full_elec.yaml", draw_dag=False)
    # df_full_elec["battery_pack_e_cum_kWh"] = df_full_elec["battery_pack_e_cum_J"] / j_to_kwh
    
    # ---- 4) H2 - pile combustible
    # df_h2, units_h2 = process("config_H2.yaml", draw_dag=False)
    # df_h2["h2_tank_e_cum_kWh"] = df_h2["h2_tank_e_cum_J"] / j_to_kwh
    # df_h2["h2_tank_masse_cum_kg"] = df_h2["h2_tank_e_cum_kWh"] / densite_energetique_h2
    
    # ---- 5) Test UI
    df_ui, units_ui = process("config_from_UI.yaml", draw_dag=False)
