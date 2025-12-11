# cgn_model/energy_solver/run_dag.py

from __future__ import annotations
import numpy as np
from typing import Mapping
from cgn_model.energy_solver import SolverDAG


def _pos(x: np.ndarray) -> np.ndarray:
    return np.maximum(x, 0.0)

def _neg_mag(x: np.ndarray) -> np.ndarray:
    """Magnitude des déficits: (-x)+ == max(-x,0)."""
    return np.maximum(-x, 0.0)

def prepare_state(
    solver: SolverDAG,
    profiles: Mapping[str, np.ndarray] | Mapping[str, tuple[str, np.ndarray]],
    *,
    check_bus: bool = True,        # vérifie que le bus fourni (si présent) matche l’input
    raise_on_extra: bool = False,  # lève si des clés de profiles ne correspondent à aucun input
) -> int:
    """
    Applique les inputs et (ré)initialise les états des bus/convertisseurs.

    Accepte deux formats pour `profiles` :
      - {input_id: array}
      - {input_id: (bus_id, array)}

    Effets :
      - Réinitialise buses.net_w et buses.ledger
      - Réinitialise converters.p_in_w et p_out_w
      - Affecte SignedInput.profile pour chaque input
      - Agrège chaque profil sur le bus associé (net_w) et log dans ledger ("in:<input_id>")
    Retourne :
      - N (longueur temporelle commune à tous les profils)
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

    # 2) Réinitialiser l'état des bus
    for b in solver.buses.values():
        b.net_w = np.zeros(N, dtype=float)
        b.ledger.clear()

    # 3) Réinitialiser les logs des convertisseurs
    for c in solver.converters.values():
        c.p_in_w = np.zeros(N, dtype=float)
        c.p_out_w = np.zeros(N, dtype=float)

    # 4) Attacher/appliquer les inputs et logger sur les bus
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
