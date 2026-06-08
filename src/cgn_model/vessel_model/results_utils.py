# cgn_model/vessel_model/results_utils.py

"""
Helpers de nommage des colonnes de résultats.

Ces fonctions ne réalisent pas de conversion physique d'unités. Elles servent
uniquement à produire des noms de colonnes stables pour les DataFrames exportés
par `Vessel.results_dataframe()`.

Convention :
- les colonnes portent un suffixe d'unité (`_W`, `_J`, `_kg`, etc.) ;
- les unités non directement compatibles avec un nom de colonne sont normalisées
  (`kg/s` -> `kg_per_s`) ;
- les colonnes issues de `StorageResult.to_dataframe()` peuvent être préfixées
  par l'identifiant du stockage sans dupliquer deux fois le suffixe d'unité.
"""

__all__ = [
    "clean_unit_syntax",
    "results_col_name",
    "unit_from_storage_col",
    "strip_storage_unit_suffix",
]


def clean_unit_syntax(unit: str | None) -> str | None:
    """
    Normalise une unité pour l'utiliser dans un nom de colonne.

    Parameters
    ----------
    unit : str | None
        Unité brute (`W`, `kg/s`, `m3`, `-`, etc.).

    Returns
    -------
    str | None
        Unité compatible avec un nom de colonne, ou None si aucune unité n'est
        fournie.

    Examples
    --------
    - `kg/s` devient `kg_per_s`
    - `-` devient `unitless`
    """
    if unit is None:
        return None
    u = unit.strip()
    if u == "" or u == "-":
        return "unitless"
    u = u.replace("/", "_per_")
    u = u.replace(" ", "")
    u = u.replace("*", "_")
    u = u.replace("^", "")
    u = u.replace("(", "").replace(")", "")
    return u


def results_col_name(base: str, unit: str | None) -> str:
    """
    Construit un nom de colonne à partir d'un nom de base et d'une unité.

    Parameters
    ----------
    base : str
        Nom logique de la grandeur.
    unit : str | None
        Unité à ajouter en suffixe.

    Returns
    -------
    str
        Nom de colonne final. Exemple : `converter_motor_out_W`.
    """
    u = clean_unit_syntax(unit)
    if u is None:
        return base
    return f"{base}_{u}"

def unit_from_storage_col(col: str) -> str | None:
    """
    Déduit l'unité d'une colonne produite par `StorageResult.to_dataframe()`.

    Parameters
    ----------
    col : str
        Nom de colonne court du DataFrame de stockage (`p_W`, `e_cum_J`, etc.).

    Returns
    -------
    str | None
        Unité détectée, ou None si la colonne ne suit pas une convention connue.
    """
    if col == "t_s":
        return "s"
    if col.endswith("_W"):
        return "W"
    if col.endswith("_kWh"):
        return "kWh"
    if col.endswith("_J"):
        return "J"
    if col.endswith("_kg"):
        return "kg"
    if col.endswith("_kg_per_s"):
        return "kg/s"
    if col.endswith("_m3"):
        return "m3"
    if col.endswith("_m3_per_s"):
        return "m3/s"
    if col.endswith("_l"):
        return "l"
    if col.endswith("_l_per_s"):
        return "l/s"
    return None


def strip_storage_unit_suffix(col: str, unit: str | None) -> str:
    """
    Retire le suffixe d'unité d'une colonne de stockage.

    Parameters
    ----------
    col : str
        Nom de colonne issu de `StorageResult.to_dataframe()`.
    unit : str | None
        Unité détectée par `unit_from_storage_col`.

    Returns
    -------
    str
        Nom de base sans suffixe d'unité. Exemple : `e_cum_J` -> `e_cum`.

    Notes
    -----
    Cette étape évite de produire des noms comme
    `storage_fuel_tank_e_cum_J_J` lors de l'ajout du préfixe storage et du
    suffixe d'unité global.
    """
    if unit == "s" and col.endswith("_s"):
        return col[:-2]
    if unit == "W" and col.endswith("_W"):
        return col[:-2]
    if unit == "kWh" and col.endswith("_kWh"):
        return col[:-4]
    if unit == "J" and col.endswith("_J"):
        return col[:-2]
    if unit == "kg" and col.endswith("_kg"):
        return col[:-3]
    if unit == "kg/s" and col.endswith("_kg_per_s"):
        return col[:-9]
    if unit == "m3" and col.endswith("_m3"):
        return col[:-3]
    if unit == "m3/s" and col.endswith("_m3_per_s"):
        return col[:-9]
    if unit == "l" and col.endswith("_l"):
        return col[:-2]
    if unit == "l/s" and col.endswith("_l_per_s"):
        return col[:-8]
    return col
