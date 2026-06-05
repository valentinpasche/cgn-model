# Script demo, configurations types

from pathlib import Path


example_dir = Path(__file__).resolve().parent

from cgn_model.vessel_model import Vessel


def process(config_file, draw_dag=False):

    yaml_text = (example_dir / config_file).read_text(encoding="utf-8")
    
    vessel = Vessel.from_yaml(yaml_text)
    vessel.run()
    
    if draw_dag:
        vessel.solver.draw_dag()
    
    df = vessel.results_dataframe()
    df_meta = df.attrs["units"]
    
    return df, df_meta, vessel

# --------------------------- Demo ---------------------------
if __name__ == "__main__":
    
    # ---- 1) Diesel-Electrique
    df_de, units_de, vessel_de = process("config_DE.yaml", draw_dag=False)
    
    # ---- 2) Vapeur
    df_steam, units_steam, _ = process("config_steam.yaml", draw_dag=False)
    
    # ---- 3) Full-electrique
    df_full_elec, units_full_elec, _ = process("config_full_elec.yaml", draw_dag=False)
    
    # ---- 4) H2 - pile combustible
    df_h2, units_h2, _ = process("config_H2.yaml", draw_dag=False)
    
    # ---- 5) Test UI
    df_ui, units_ui, vessel_ui = process("config_from_UI.yaml", draw_dag=False)
