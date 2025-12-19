# cgn_model/vessel_model/__init__.py

"""
API publique vessel_model.
"""

# Re-export the friendly public API
from .vessel import Vessel

# Keep the surface area explicit
__all__ = [
    "Vessel",
]

