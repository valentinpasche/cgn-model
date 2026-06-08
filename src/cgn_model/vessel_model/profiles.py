# cgn_model/vessel_model/profiles.py

"""
Profils runtime du `Vessel` et helpers de construction.

Ce module regroupe les objets et fonctions liés aux profils d'entrée du modèle :

- `Profile` : conteneur runtime d'un signal brut déclaré dans le YAML ;
- `_load_csv_column` : chargement d'une série numérique depuis un CSV ;
- `_build_nav_speed` : génération d'un profil de vitesse depuis les horaires CGN ;
- `_pick_master_id` : choix du profil maître qui fixe l'horizon temporel.

Les fonctions restent préfixées par `_` car elles sont utilisées comme helpers
internes par `Vessel`. Elles sont isolées ici pour alléger `vessel.py` et rendre
le pipeline de construction des profils plus lisible.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray

from cgn_model.navigation import Croisiere, SpeedProfileParams
from cgn_model.vessel_model.config import (
    ProfileCfg,            # Union discriminée: constant/series/file/nav_speed
    NavSelect,
    NavParams,
)

type FArray = NDArray[np.floating]

__all__ = ["Profile"]


# ---------------- Types & runtime entities ----------------
@dataclass
class Profile:
    """
    Profil brut tel que declare cote YAML.

    Un `Profile` correspond a une source de signal avant transformation par un
    adapter. Il porte uniquement l'identifiant, l'unite declaree et le tableau de
    valeurs deja construit.

    Attributes
    ----------
    id : str
        Identifiant du profil.
    unit : str
        Unite declaree (ex. "kn", "W", "m/s").
    data : numpy.ndarray
        Profil 1D en float64.
    """
    id: str
    unit: str
    data: FArray


# ---------- Helpers I/O & navigation ----------
def _load_csv_column(
    file: str,
    column: str | None,
    sep: str | None = None,           # <- override possible
    decimal: str = ".",               # <- "." ou ","
    encoding: str = "utf-8-sig",      # gère le BOM Excel
) -> FArray:
    """
    Charge une colonne numerique d'un CSV en float64.

    Parameters
    ----------
    file : str
        Chemin du fichier CSV.
    column : str | None
        Nom de colonne; si None, utilise la premiere colonne.
    sep : str | None, optional
        Separateur CSV. None = auto-detection.
    decimal : str, optional
        Separateur decimal ("." ou ",").
    encoding : str, optional
        Encodage (ex. "utf-8-sig" pour BOM Excel).

    Returns
    -------
    numpy.ndarray
        Serie 1D en float64.
    """
    try:
        import pandas as pd  # type: ignore

        # Auto-détection via l’engine Python si sep=None
        if sep is None:
            df = pd.read_csv(file, sep=None, engine="python", decimal=decimal, encoding=encoding)
        else:
            df = pd.read_csv(file, sep=sep, decimal=decimal, encoding=encoding)

        col = column or (df.columns[0] if len(df.columns) else None)
        if not col or col not in df.columns:
            raise ValueError(
                f"Colonne {column!r} introuvable dans {file!r}. "
                f"Colonnes: {list(df.columns)!r}"
            )

        arr = df[col].to_numpy(dtype="float64", na_value=np.nan)
        if np.isnan(arr).any():
            raise ValueError(f"Valeurs non numériques/NA dans {file!r} colonne {col!r}.")
        return arr  # type: ignore[return-value]

    except ModuleNotFoundError:
        import csv
        # Fallback: tente Sniffer si sep non fourni
        with open(file, "r", encoding=encoding, newline="") as f:
            if sep is None:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
                    sep = dialect.delimiter
                except csv.Error:
                    sep = ","  # défaut raisonnable
            reader = csv.DictReader(f, delimiter=sep)
            if reader.fieldnames is None:
                raise ValueError(
                    f"CSV {file!r} sans en-tête; fournis 'column' ou installe pandas."
                )
            col = column or reader.fieldnames[0]
            if col not in reader.fieldnames:
                raise ValueError(
                    f"Colonne {column!r} introuvable dans {file!r}. "
                    f"Colonnes: {reader.fieldnames!r}"
                )

            vals: list[float] = []
            for row in reader:
                s = row[col]
                # gérer décimale ","
                if decimal == ",":
                    s = s.replace(",", ".")
                try:
                    vals.append(float(s))
                except ValueError as e:
                    raise ValueError(
                        f"Valeur non numérique dans {file!r} colonne {col!r}: {row[col]!r}"
                    ) from e
        return np.asarray(vals, dtype=np.float64)


def _build_nav_speed(
    *,
    source: str,                # ex: "cgn_croisieres/all"
    select: NavSelect,          # by="cruise" | "course" | "leg"
    params: NavParams,          # acc/dec/v_croisiere/allow_delay
    dt: float,                  # pas global [s]
) -> FArray:
    """
    Construit un profil de vitesse [m/s] depuis le module navigation.

    Parameters
    ----------
    source : str
        Source des horaires (ex. "cgn_croisieres/all").
    select : NavSelect
        Criteres de selection (cruise, course, leg).
    params : NavParams
        Parametres MRUA (acc, dec, v_croisiere, allow_delay).
    dt : float
        Pas de temps global [s].

    Returns
    -------
    numpy.ndarray
        Profil de vitesse [m/s].

    Notes
    -----
    Cette fonction fait le lien entre la configuration YAML `kind: nav_speed` et
    les objets du module `navigation`. Elle sélectionne une croisière, une course
    ou une étape, applique les paramètres MRUA puis récupère le profil généré.
    """
    # 1) charger les croisières depuis la "source"
    #    Pour l’instant on supporte "cgn_croisieres/<which>"
    if not source.startswith("cgn_croisieres/"):
        raise ValueError(f"source nav_speed non supportée: {source!r} (attendu 'cgn_croisieres/<which>')")
    which = source.split("/", 1)[1] or "all"
    cruises: list[Croisiere] = Croisiere.from_cgn_croisiere_csv(which)

    # 2) sélectionner l’objet navigation cible
    target = None

    if select.by == "cruise":
        name = select.cruise_name
        for cr in cruises:
            if getattr(cr, "nom", None) == name:
                target = cr
                break
        if target is None:
            raise ValueError(f"Croisière {name!r} introuvable dans {which!r}.")

    elif select.by == "course":
        num = select.course_no
        for cr in cruises:
            for c in getattr(cr, "courses", []):
                if getattr(c, "numero", None) == num:
                    target = c
                    break
            if target is not None:
                break
        if target is None:
            raise ValueError(f"Course n°{num} introuvable dans {which!r}.")

    elif select.by == "leg":
        leg = select.leg or {}
        fport = leg.get("from_port"); tport = leg.get("to_port")
        if not fport or not tport:
            raise ValueError("select.leg doit contenir {from_port, to_port}.")
        for cr in cruises:
            # Etapes dans les courses
            for c in getattr(cr, "courses", []):
                for e in getattr(c, "etapes", []):
                    if getattr(e, "from_port", None) == fport and getattr(e, "to_port", None) == tport:
                        target = e
                        break
                if target is not None:
                    break
            if target is not None:
                break
            # Etapes "pauses" éventuelles (si pertinent)
            for e in getattr(cr, "pauses", []) or []:
                if getattr(e, "from_port", None) == fport and getattr(e, "to_port", None) == tport:
                    target = e
                    break
            if target is not None:
                break
        if target is None:
            raise ValueError(f"Étape {fport!r}->{tport!r} introuvable dans {which!r}.")

    else:
        raise NotImplementedError(f"select.by={select.by!r} non supporté")
    
    # 3) Fusion des paramètres : dt = global ; le reste, override si fourni
    sp = SpeedProfileParams(dt=float(dt)) # << défaut de référence ici pour dt
    if params.acc is not None:         sp.acc = float(params.acc)
    if params.dec is not None:         sp.dec = float(params.dec)
    if params.v_croisiere is not None: sp.v_croisiere = float(params.v_croisiere)
    if params.allow_delay is not None: sp.allow_delay = bool(params.allow_delay)
    
    # propage la méthode .speed_profil(sp) selon le type (Croisiere/Course/Etape)
    target.speed_profile(sp)
    arr = getattr(target, "profile", None)
    if arr is None:
        raise RuntimeError("Le module navigation n’a pas produit de 'profile'.")
    return np.asarray(arr, dtype=np.float64)


# ---------- Helpers de "preview" et choix du maître ----------
def _pick_master_id(profiles_cfg: list[ProfileCfg]) -> str:
    """
    Choisit l'ID du profil maitre sans le construire.

    Parameters
    ----------
    profiles_cfg : list[ProfileCfg]
        Liste des profils declares.

    Returns
    -------
    str
        ID du profil maitre.

    Notes
    -----
    Priorite de selection:
    - premier p.master == True (mais pas "constant")
    - premier "nav_speed"
    - premier "series" ou "file"
    - sinon -> erreur (tous constants => ambigu sans longueur de reference)

    Le profil maitre fixe l'horizon temporel N utilisé ensuite pour vérifier ou
    étendre les autres profils.
    """
    # 1) master explicite
    for p in profiles_cfg:
        if getattr(p, "master", False):
            if p.kind == "constant":
                raise ValueError(
                    f"Profil maître {p.id!r} est 'constant' : une longueur de référence est nécessaire "
                    "(déclare un nav_speed/series/file maître)."
                )
            return p.id

    # 2) premier nav_speed
    for p in profiles_cfg:
        if p.kind == "nav_speed":
            return p.id

    # 3) premier series/file
    for p in profiles_cfg:
        if p.kind in ("series", "file"):
            return p.id

    # 4) sinon
    raise ValueError(
        "Aucune longueur de référence trouvée (tous les profils sont 'constant'). "
        "Déclare un 'nav_speed' ou 'series/file'."
    )
