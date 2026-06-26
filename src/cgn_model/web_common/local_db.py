"""
Gestion des bases SQLite utilisateur pour les interfaces web.

Les templates restent inclus dans le package Python. Les bases modifiables par
l'utilisateur sont creees dans un dossier local, hors du code installe.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import os
from pathlib import Path
import shutil


DATA_DIR_ENV = "CGN_MODEL_DATA_DIR"
APP_DIR_NAME = "CGN-model"


@dataclass(frozen=True)
class LocalDb:
    """Chemins d'une base SQLite locale et de son template package."""

    path: Path
    template: Path


def _ensure_writable_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
    finally:
        if probe.exists():
            probe.unlink()
    return path


def _default_data_dir() -> Path:
    env_value = os.environ.get(DATA_DIR_ENV)
    if env_value and env_value.strip():
        raw = Path(env_value.strip()).expanduser()
        try:
            return _ensure_writable_dir(raw)
        except OSError as exc:
            raise RuntimeError(
                f"Le dossier defini par {DATA_DIR_ENV} n'est pas accessible en ecriture: {raw}"
            ) from exc

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data and local_app_data.strip():
        try:
            return _ensure_writable_dir(Path(local_app_data) / APP_DIR_NAME)
        except OSError:
            pass

    fallback = Path.home() / ".cgn-model"
    try:
        return _ensure_writable_dir(fallback)
    except OSError as exc:
        raise RuntimeError(
            "Aucun dossier local accessible n'a pu etre trouve pour les bases SQLite. "
            f"Definissez {DATA_DIR_ENV} vers un dossier accessible en ecriture."
        ) from exc


def user_data_dir() -> Path:
    """Retourne le dossier local utilise pour les donnees utilisateur."""

    return _default_data_dir()


def local_db(
    *,
    package: str,
    template_name: str,
    db_name: str,
) -> LocalDb:
    """
    Retourne le chemin DB utilisateur et copie le template au premier usage.

    Parameters
    ----------
    package:
        Package contenant le dossier `data` et le template.
    template_name:
        Nom du fichier template inclus dans le package.
    db_name:
        Nom du fichier SQLite utilisateur a creer/utiliser.
    """

    template = resources.files(package).joinpath("data", template_name)
    data_dir = user_data_dir()
    db_path = data_dir / db_name
    if not db_path.exists():
        with resources.as_file(template) as template_path:
            shutil.copyfile(template_path, db_path)
    return LocalDb(path=db_path, template=Path(str(template)))
