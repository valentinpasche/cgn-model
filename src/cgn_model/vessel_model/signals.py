# cgn_model/vessel_model/signals.py

"""
Types runtime et conventions de signe pour les signaux du `Vessel`.

Ce module contient les petits conteneurs utilisés entre la matérialisation des
profils/adapters et l'application des inputs au `SolverDAG`.

Un signal est représenté par un tuple `(array, unit)`. Un `InputBind` indique
quelle source de signal alimente quel input solver, avec quelle convention de
signe.

Le module contient aussi les helpers qui appliquent et contrôlent cette
convention de signe avant l'appel à `prepare_state`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import numpy as np
from numpy.typing import NDArray
import warnings

type FArray = NDArray[np.floating]

# ---------------- Types & runtime entities ----------------
@dataclass
class InputBind:
    """
    Liaison input solver -> source (profil ou adapter).

    `InputBind` est la représentation runtime d'une entrée de la section YAML
    `inputs`. Il ne contient pas encore le profil signé final : il décrit le
    câblage entre une source (`Profile` ou adapter matérialisé) et un input du
    solver.

    Attributes
    ----------
    id : str
        Identifiant de l'input (cote solver).
    bus : str
        Bus cible (cote solver).
    source : str
        ID d'un Profile ou d'un Adapter.
    sign : str
        Convention de signe (consume/inject/as_is).
    scale : float
        Facteur d'echelle applique au profil.
    """
    id: str
    bus: str
    source: str
    sign: str
    scale: float = 1.0


type Signals = dict[str, tuple[FArray, str]]
"""
Mapping des signaux matérialisés.

Clé : identifiant d'un profile ou d'un adapter.
Valeur : tuple `(array, unit)` avec un tableau 1D et son unité déclarée.
"""


def _apply_sign_policy(arr: FArray, policy: str, scale: float | int | None) -> FArray:
    """
    Applique la convention de signe d'un input avant injection dans le solver.

    Cette fonction est utilisée par `Vessel.build_solver_inputs()`, au dernier
    moment avant la transmission des profils au `SolverDAG`.

    Parameters
    ----------
    arr : FArray
        Signal 1D source, dans son unite courante apres conversion eventuelle.
    policy : {"consume", "inject", "as_is"}
        Convention de signe cote bus solver.
        ``consume`` rend le profil negatif, ``inject`` le rend positif et
        ``as_is`` conserve le signe fourni.
    scale : float | int | None
        Facteur multiplicatif optionnel applique avant la convention de signe.

    Returns
    -------
    FArray
        Signal signe selon la convention du bilan de bus.

    Notes
    -----
    La convention numerique du solver est : puissance positive = injection sur
    un bus, puissance negative = demande ou retrait sur ce bus.

    La convention YAML est donc traduite ainsi :
    - `consume` : le signal est converti en demande, donc force en negatif ;
    - `inject` : le signal est converti en apport, donc force en positif ;
    - `as_is`  : le signe du signal source est conserve.

    Le facteur `scale`, s'il est fourni, est applique avant cette politique de
    signe. Un `scale` negatif peut donc inverser le sens physique attendu et
    declencher un warning plus loin dans le pipeline.
    """
    arr = np.asarray(arr, dtype=np.float64)
    if scale is not None:
        arr = arr * float(scale)
    
    if policy == "consume":  # négatif
        return -arr
    if policy == "inject":   # positif
        return +arr
    if policy == "as_is":
        return arr
    raise ValueError(f"sign policy inconnue: {policy!r}")


def _warn_inconsistent_sign(
    arr: np.ndarray,
    expected: Literal["consume", "inject"],
    *,
    eps: float = 1e-9,      # tolerance pour "quasi zero"
    min_count_warn: int = 1, # a partir de combien de points "mauvais signe" on previent
) -> tuple[int, int, float]:
    """
    Detecte les incoherences de signe sur un profil.

    Cette fonction ne modifie pas le profil. Elle signale uniquement les cas où
    le résultat signé ne correspond pas à la convention attendue par l'input.

    Parameters
    ----------
    arr : numpy.ndarray
        Profil 1D.
    expected : {"consume", "inject"}
        Signe attendu.
    eps : float, optional
        Tolerance pour quasi-zero.
    min_count_warn : int, optional
        Seuil minimal pour emettre un warning.

    Returns
    -------
    tuple[int, int, float]
        (total_utiles, nb_mauvais, frac_mauvais).

    Notes
    -----
    - expected = "consume" -> on attend des valeurs <= 0
    - expected = "inject"  -> on attend des valeurs >= 0
    """
    nz = np.abs(arr) > eps            # on ignore ~0
    total = int(nz.sum())
    if total == 0:
        return 0, 0, 0.0

    if expected == "consume":
        wrong_mask = arr[nz] > 0
    else:  # 'inject'
        wrong_mask = arr[nz] < 0

    wrong = int(wrong_mask.sum())
    frac = wrong / total if total else 0.0

    if wrong >= min_count_warn:
        warnings.warn(
            f"Signe inattendu pour sign={expected}: {wrong}/{total} "
            f"échantillons (~{frac*100:.3f}%). "
            f"min={arr.min():.3g}, max={arr.max():.3g}",
            stacklevel=2,
        )

    return total, wrong, frac
