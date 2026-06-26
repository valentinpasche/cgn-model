"""
Chargement d'un YAML exemple pour le MVP web.
"""

from __future__ import annotations

from importlib import resources


def load_default_yaml() -> str:
    """
    Retourne le contenu du YAML d'exemple V1.
    """
    return resources.files("cgn_model.web_mvp").joinpath(
        "data", "config_vevey_croisiere.yaml"
    ).read_text(encoding="utf-8")
