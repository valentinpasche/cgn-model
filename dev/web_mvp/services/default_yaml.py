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
    root = here.parents[3]
    cfg_path = root / "examples" / "cgn_model_v1_251222" / "config_v1.yaml"
    return cfg_path.read_text(encoding="utf-8")
