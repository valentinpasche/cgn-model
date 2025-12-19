# cgn_model/navigation/__init__.py

"""
API navigation : etapes, courses, croisieres et profils de vitesse.
"""

from .cruise_model import Etape, Course, Croisiere, SpeedProfileParams

__all__ = ["Etape", "Course", "Croisiere", "SpeedProfileParams"]
