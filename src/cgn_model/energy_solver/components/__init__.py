# cgn_model/energy_solver/components/__init__.py

"""
Composants du solver : registre des convertisseurs.

Pour ajouter un convertisseur, modifier uniquement components/converters.py.
"""

from .converters import (
    ConverterABC,
    build_converter_from_cfg,
)

__all__ = [
    "ConverterABC",
    "build_converter_from_cfg",
]
