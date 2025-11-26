# cgn_model/energy_solver/run_dag.py

from __future__ import annotations
import numpy as np
from typing import Mapping
from cgn_model.energy_solver import SolverDAG


def _check_and_get_len(profiles: Mapping[str, np.ndarray]) -> int:
    if not profiles:
        raise ValueError("Aucun profil d'input fourni.")
    lens = {k: np.asarray(v).shape for k, v in profiles.items()}
    shapes = set(lens.values())
    if len(shapes) != 1 or len(next(iter(shapes))) != 1:
        raise ValueError(f"Tous les profils doivent être 1D et de même taille, reçu: {lens}")
    return next(iter(shapes))[0]

def _pos(x: np.ndarray) -> np.ndarray:
    return np.maximum(x, 0.0)

def _neg_mag(x: np.ndarray) -> np.ndarray:
    """Magnitude des déficits: (-x)+ == max(-x,0)."""
    return np.maximum(-x, 0.0)

def prepare_state(solver: SolverDAG, profiles: Mapping[str, np.ndarray]) -> int:
    """
    Applique les inputs et (ré)initialise les états des bus/convertisseurs.
    - profiles: dict[input_id -> profil signé]
    Retourne N (longueur temporelle).
    """
    N = _check_and_get_len(profiles)

    # init bus states
    for b in solver.buses.values():
        b.net_w = np.zeros(N, dtype=float)
        b.ledger.clear()

    # init conv logs
    for c in solver.converters.values():
        c.p_in_w = np.zeros(N, dtype=float)
        c.p_out_w = np.zeros(N, dtype=float)

    # attach/applique inputs
    for s in solver.inputs.values():
        try:
            prof = np.asarray(profiles[s.id], dtype=float)
        except KeyError as e:
            raise KeyError(f"Profil manquant pour l'input '{s.id}'") from e
        if prof.shape != (N,):
            raise ValueError(f"Profil '{s.id}' a la mauvaise taille: {prof.shape}, attendu {(N,)}")
        s.profile = prof
        solver.buses[s.bus].net_w += prof
        # log côté bus
        solver.buses[s.bus].ledger[f"in:{s.id}"] = prof

    return N

def run_vector(solver: SolverDAG) -> None:
    """
    Propage les flux sur le DAG en mode vectoriel.
    Convention: profil > 0 = injection sur un bus, < 0 = demande.
    - mode 'inverse': on couvre d'abord les déficits en aval (on remonte la chaîne).
    - mode 'forward': on pousse les surplus disponibles en amont vers l'aval (capé par le besoin).
    Effets:
      - maj solver.buses[...].net_w
      - maj conv.p_in_w / conv.p_out_w
      - ledger minimal sur les bus (optionnel)
    """
    if solver.mode == "inverse":
        for (u, v), conv_id in solver.plan:
            conv = solver.converters[conv_id]
            bus_u = solver.buses[u]
            bus_v = solver.buses[v]

            need_v = _neg_mag(bus_v.net_w)              # besoin à v (déficit)
            p_out = need_v                               # on cherche à annuler le déficit
            p_in  = conv.inverse(p_out)

            # applique
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



""" Info GPT pour la suite (13.11.2025)

Notes / conventions
- Signes : + injecte sur un bus, - consomme.
- inverse : on “remonte” et on couvre les déficits à chaque étape (plus simple pour des demandes imposées).
- forward : on “descend” et on pousse les surplus (capés par le besoin aval).
- Résidus possibles : s’il reste un déficit en racine (aucun amont) → le net_w final sera encore < 0 (c’est un besoin non satisfait). Idem pour un surplus non évacué.

C’est volontairement minimal. Quand tu voudras, faire ce qui est en dessous, on étendra ce moteur.:
- contraindre des puissances max par convertisseur
- gérer des stockages (états dynamiques)
- enregistrer des bilans plus riches
"""