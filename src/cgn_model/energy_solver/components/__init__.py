# cgn_model/energy_solver/components/__init__.py

"""Components registry (converters, later maybe inputs/buses)."""

"""
Le module "components.converters" est le SEUL endroit à modifier quand vous ajoutez un nouveau
type de convertisseur. Le reste du système (config, solver_dag) n’a pas
besoin d’être changé.
Les autres composants de SolverDAG, "inputs" et "buses", peuvent être déclinés,
déplacés et adaptés, de la même manière que les "converters" dans ce module.
"""

from .converters import (
    ConverterABC,
    build_converter_from_cfg,
)

__all__ = [
    "ConverterABC",
    "build_converter_from_cfg",
]
