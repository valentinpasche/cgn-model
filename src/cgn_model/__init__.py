# cgn_model/__init__.py

"""
Paquet principal cgn_model.

Expose les sous-modules energy_solver, vessel_model et navigation, ainsi que le
point d'entree metier principal `Vessel`.
"""

__version__ = "1.2"

__all__ = ["Vessel", "__version__"]


def __getattr__(name: str):
    """
    Charge l'API metier principale a la demande.

    Cela permet `from cgn_model import Vessel` sans importer tout le modele
    vessel lors d'un simple `import cgn_model`.
    """
    if name == "Vessel":
        from cgn_model.vessel_model import Vessel

        return Vessel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
