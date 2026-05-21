# cgn_model/energy_solver/run_dag.py

"""
Execution vectorielle du solveur DAG.

Ce module prepare les inputs et propage les flux selon le mode du solver.
"""

from __future__ import annotations
import numpy as np
from typing import Mapping
from cgn_model.energy_solver import SolverDAG


def _pos(x: np.ndarray) -> np.ndarray:
    """
    Partie positive de x (max(x, 0)).

    Parameters
    ----------
    x : numpy.ndarray
        Tableau d'entree.

    Returns
    -------
    numpy.ndarray
        Tableau avec les valeurs negatives tronquees a 0.
    """
    return np.maximum(x, 0.0)

def _neg_mag(x: np.ndarray) -> np.ndarray:
    """
    Magnitude des deficits: (-x)+ == max(-x, 0).

    Parameters
    ----------
    x : numpy.ndarray
        Tableau d'entree.

    Returns
    -------
    numpy.ndarray
        Magnitude des valeurs negatives.
    """
    return np.maximum(-x, 0.0)

def prepare_state(
    solver: SolverDAG,
    profiles: Mapping[str, np.ndarray] | Mapping[str, tuple[str, np.ndarray]],
    *,
    check_bus: bool = True,        # vérifie que le bus fourni (si présent) matche l’input
    raise_on_extra: bool = False,  # lève si des clés de profiles ne correspondent à aucun input
) -> int:
    """
    Applique les inputs et reinitialise les etats du solver.

    Parameters
    ----------
    solver : SolverDAG
        Instance du solveur prepare.
    profiles : Mapping[str, numpy.ndarray] | Mapping[str, tuple[str, numpy.ndarray]]
        Profils des inputs. Deux formats acceptes :
        - {input_id: array}
        - {input_id: (bus_id, array)}
    check_bus : bool, optional
        Verifie que le bus fourni correspond a l'input.
    raise_on_extra : bool, optional
        Leve si des cles de profiles ne correspondent a aucun input.

    Returns
    -------
    int
        Longueur temporelle commune a tous les profils.

    Notes
    -----
    Effets de bord :
    - reinitialise buses.net_w et buses.ledger
    - reinitialise converters.p_in_w et p_out_w
    - attache SignedInput.profile pour chaque input
    - agrege chaque profil sur le bus associe (ledger "in:<input_id>")
    """
    # Optionnel : détecter des profils "en trop"
    if raise_on_extra:
        extra = set(profiles.keys()) - set(solver.inputs.keys())
        if extra:
            raise KeyError(f"Profils inconnus (aucun input correspondant côté solver): {sorted(extra)!r}")

    # 1) Préparer/valider tous les arrays et déterminer N
    prepared: dict[str, np.ndarray] = {}
    N: int | None = None

    for input_id, s in solver.inputs.items():
        if input_id not in profiles:
            raise KeyError(f"Profil manquant pour l'input {input_id!r}")

        payload = profiles[input_id]
        if isinstance(payload, tuple) and len(payload) == 2:
            bus_id, arr = payload
            if check_bus and bus_id != s.bus:
                raise ValueError(
                    f"Profil {input_id!r} fourni pour bus {bus_id!r}, "
                    f"mais l'input est connecté à {s.bus!r}."
                )
        else:
            arr = payload

        arr = np.asarray(arr, dtype=float)
        if arr.ndim != 1:
            raise ValueError(f"Profil {input_id!r} doit être 1D, reçu shape={arr.shape}.")

        if N is None:
            N = int(arr.shape[0])
        elif arr.shape[0] != N:
            raise ValueError(f"Longueur incohérente pour {input_id!r}: {arr.shape[0]} != {N}.")

        prepared[input_id] = arr

    if N is None:
        raise ValueError("Aucun profil fourni à prepare_state().")

    # Chaque appel repart d'un etat vierge: les profils d'input sont la seule
    # source de net_w initiale, et le ledger garde la trace par contribution.
    for b in solver.buses.values():
        b.net_w = np.zeros(N, dtype=float)
        b.ledger.clear()

    # 3) Réinitialiser les logs des convertisseurs
    for c in solver.converters.values():
        c.p_in_w = np.zeros(N, dtype=float)
        c.p_out_w = np.zeros(N, dtype=float)

    # Les inputs sont deja signes par Vessel: ici on additionne simplement les
    # puissances [W] sur leur bus cible.
    for input_id, arr in prepared.items():
        s = solver.inputs[input_id]
        s.profile = arr
        bus = solver.buses[s.bus]
        bus.net_w += arr
        bus.ledger[f"in:{input_id}"] = arr

    return N

def run_vector(solver: SolverDAG) -> None:
    """
    Propage les flux sur le DAG en mode vectoriel.

    Parameters
    ----------
    solver : SolverDAG
        Instance du solveur preparee avec des profils.

    Notes
    -----
    Convention : profil > 0 = injection sur un bus, < 0 = demande.
    - mode "inverse" : couvre les deficits en aval (remonte la chaine).
    - mode "forward" : pousse les surplus amont vers l'aval (borne par le besoin).
    - Les grandeurs propagees sont des puissances instantanees [W].

    Effets
    ------
    - maj solver.buses[...].net_w
    - maj conv.p_in_w / conv.p_out_w
    - ledger minimal sur les bus (optionnel)
    """
    if solver.mode == "inverse":
        for (u, v), conv_id in solver.plan:
            conv = solver.converters[conv_id]
            bus_u = solver.buses[u]
            bus_v = solver.buses[v]

            # En inverse, le deficit aval fixe la sortie requise; l'entree est
            # calculee par le rendement inverse du convertisseur.
            need_v = _neg_mag(bus_v.net_w)              # besoin à v (déficit)
            p_out = need_v                               # on cherche à annuler le déficit
            p_in  = conv.inverse(p_out)

            # Effet bilan: l'amont fournit p_in (retrait, donc -p_in), l'aval
            # recoit p_out (injection, donc +p_out).
            conv.p_in_w  += p_in
            conv.p_out_w += p_out
            bus_u.net_w  -= p_in
            bus_v.net_w  += p_out

            # logs (optionnels)
            bus_u.ledger.setdefault(f"conv_out:{conv_id}", np.zeros_like(p_in))
            bus_u.ledger[f"conv_out:{conv_id}"] += -p_in
            bus_v.ledger.setdefault(f"conv_in:{conv_id}", np.zeros_like(p_out))
            bus_v.ledger[f"conv_in:{conv_id}"] += p_out

    elif solver.mode == "forward":
        # TODO: valider le mode forward sur un cas physique de reference avant
        # de retirer cette protection.
        # Protection calcul non vérifié, à supprimer en temps voulu.
        raise NotImplementedError(f"Mode solver `{solver.mode!r}` non vérifié. Ne pas utiliser pour l'instant.")
        
        # Déroulement prévu, ne pas supprimer
        for (u, v), conv_id in solver.plan:
            conv = solver.converters[conv_id]
            bus_u = solver.buses[u]
            bus_v = solver.buses[v]

            avail_u   = _pos(bus_u.net_w)                # surplus dispo à u
            need_v    = _neg_mag(bus_v.net_w)            # besoin en aval
            p_in_cap  = conv.inverse(need_v)             # input requis pour satisfaire tout le besoin
            p_in_used = np.minimum(avail_u, p_in_cap)    # on ne consomme pas plus que dispo
            p_out     = conv.forward(p_in_used)

            conv.p_in_w  += p_in_used
            conv.p_out_w += p_out
            bus_u.net_w  -= p_in_used
            bus_v.net_w  += p_out

            bus_u.ledger.setdefault(f"conv_out:{conv_id}", np.zeros_like(p_in_used))
            bus_u.ledger[f"conv_out:{conv_id}"] += -p_in_used
            bus_v.ledger.setdefault(f"conv_in:{conv_id}", np.zeros_like(p_out))
            bus_v.ledger[f"conv_in:{conv_id}"] += p_out
    else:
        raise NotImplementedError(f"Mode inconnu: {solver.mode!r}")

# Fonction utilitaire non utilisée pour l'instant dans le pipline global.
def attach_eta_profile(solver, conv_id: str, eta_series) -> None:
    """
    Attache un profil d'efficacite eta(t) a un convertisseur `variable_eta`.

    Parameters
    ----------
    solver : SolverDAG
        Solveur contenant le convertisseur cible.
    conv_id : str
        Identifiant du convertisseur a rendement variable.
    eta_series : array-like
        Profil 1D adimensionnel, valeurs attendues dans [0, 1].

    Returns
    -------
    None
        Le profil est attache par effet de bord sur le convertisseur.

    Notes
    -----
    A appeler apres la construction des inputs, pour connaitre l'horizon
    temporel N, et avant `run_vector`.
    """
    conv = solver.converters.get(conv_id)
    if conv is None:
        raise KeyError(f"Convertisseur inconnu: {conv_id!r}")
    
    if not hasattr(conv, "eta_profile"):
        raise TypeError(
            f"Le convertisseur {conv_id!r} n'accepte pas de profil η. "
            "Utilise kind='variable_eta'."
        )
    
    eta = np.asarray(eta_series, dtype=np.float64)
    if eta.ndim != 1:
        raise ValueError("eta_series doit être un vecteur 1D")
    if (eta < 0).any() or (eta > 1).any():
        # on tolère des écarts si tu veux, sinon on borne
        eta = np.clip(eta, 0.0, 1.0)
    
    conv.eta_profile = eta




