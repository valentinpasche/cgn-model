# cgn_model/energy_solver/__init__.py

"""Energy Solver – DAG preparation and config validation."""

# Re-export the friendly public API
from .solver_dag import SolverDAG
from .run_dag import prepare_state, run_vector, attach_eta_profile

# Keep the surface area explicit
__all__ = [
    "SolverDAG",
    "prepare_state",
    "run_vector",
    "attach_eta_profile",
]
