"""
Exemple autonome d'utilisation du SolverDAG, sans passer par Vessel.

Le script montre les trois étapes de l'API publique du solveur :

1. construire la topologie avec SolverDAG.from_yaml() ;
2. appliquer des profils d'inputs signes avec prepare_state() ;
3. propager les puissances avec run_vector().
"""

from pathlib import Path

import numpy as np
import pandas as pd

from cgn_model.energy_solver import SolverDAG, prepare_state, run_vector


YAML_TEXT = """
solver:
  mode: "inverse"

buses:
  - id: "shaft"
    carrier: "Mechanical"

  - id: "elec_power"
    carrier: "Electrical"

  - id: "fuel"
    carrier: "Chemical"

inputs:
  - id: "shaft_demand"
    bus: "shaft"

  - id: "hotel_load"
    bus: "elec_power"

converters:
  - id: "motor"
    from_bus: "elec_power"
    to_bus: "shaft"
    kind: "constant_eta"
    params:
      eta: 0.90

  - id: "genset"
    from_bus: "fuel"
    to_bus: "elec_power"
    kind: "constant_eta"
    params:
      eta: 0.40
"""


# Convention du solveur : une demande est negative, une injection est positive.
shaft_demand_w = -np.array(
    [0.0, 100_000.0, 300_000.0, 500_000.0, 500_000.0, 300_000.0, 100_000.0, 0.0]
)
hotel_load_w = -np.full(shaft_demand_w.shape, 80_000.0)

input_profiles = {
    "shaft_demand": ("shaft", shaft_demand_w),
    "hotel_load": ("elec_power", hotel_load_w),
}


# 1) Construction de la topologie et du plan d'execution.
solver = SolverDAG.from_yaml(YAML_TEXT)

# Affichage optionnel du graphe de visualisation.
# solver.draw_dag()

# 2) Initialisation des bus avec les profils d'inputs.
N = prepare_state(solver, input_profiles)

# 3) Resolution vectorielle du DAG en mode inverse.
run_vector(solver)


# Extraction des principaux resultats du solveur.
dt_s = 1.0
time_s = np.arange(N, dtype=float) * dt_s

results = pd.DataFrame(
    {
        "time_s": time_s,
        "shaft_demand_W": solver.inputs["shaft_demand"].profile,
        "hotel_load_W": solver.inputs["hotel_load"].profile,
        "motor_in_W": solver.converters["motor"].p_in_w,
        "motor_out_W": solver.converters["motor"].p_out_w,
        "genset_in_W": solver.converters["genset"].p_in_w,
        "genset_out_W": solver.converters["genset"].p_out_w,
        "fuel_bus_net_W": solver.buses["fuel"].net_w,
    }
)


# Controles simples du bilan et des rendements declares.
np.testing.assert_allclose(
    solver.converters["motor"].p_out_w,
    -shaft_demand_w,
)
np.testing.assert_allclose(
    solver.converters["motor"].p_in_w,
    solver.converters["motor"].p_out_w / 0.90,
)
np.testing.assert_allclose(
    solver.converters["genset"].p_out_w,
    -hotel_load_w + solver.converters["motor"].p_in_w,
)
np.testing.assert_allclose(
    solver.converters["genset"].p_in_w,
    solver.converters["genset"].p_out_w / 0.40,
)
np.testing.assert_allclose(solver.buses["shaft"].net_w, 0.0)
np.testing.assert_allclose(solver.buses["elec_power"].net_w, 0.0)


print("Plan d'execution :", solver.plan)
print()
print(results.to_string(index=False))

# Export optionnel.
example_dir = Path(__file__).resolve().parent
# results.to_csv(example_dir / "results.csv", sep=";", index=False)
