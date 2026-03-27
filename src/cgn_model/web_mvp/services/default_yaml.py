"""
Chargement d'un YAML exemple pour le MVP web.
"""

from __future__ import annotations

from pathlib import Path


def load_default_yaml() -> str:
    """
    Retourne le contenu du YAML d'exemple V1.
    """
    here = Path(__file__).resolve()
    cfg_path = here.parents[1] / "data" / "config_vevey_croisiere.yaml"
    return cfg_path.read_text(encoding="utf-8")
