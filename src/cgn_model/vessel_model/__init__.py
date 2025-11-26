# vessel_model/__init__.py

# Re-export the friendly public API
from .base import Vessel

# Keep the surface area explicit
__all__ = [
    "Vessel",
]
