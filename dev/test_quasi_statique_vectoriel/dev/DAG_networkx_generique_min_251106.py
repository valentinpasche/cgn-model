# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
import numpy as np
import yaml
import networkx as nx  # pip install networkx pyyaml

# --------------- Protocols ---------------
class SupportsInput:
    def series(self, t: np.ndarray) -> np.ndarray: ...

# --------------- Core data ---------------
@dataclass
class Bus:
    id: str
    carrier: str
    net_W: np.ndarray  # signé: + injection ; - demande
    ledger: Dict[str, np.ndarray] = field(default_factory=dict)
    def add(self, label: str, series_W: np.ndarray):
        s = np.asarray(series_W, dtype=float)
        self.net_W = self.net_W + s
        self.ledger[label] = self.ledger.get(label, np.zeros_like(self.net_W)) + s

@dataclass
class SignedInput(SupportsInput):
    """Profil signé appliqué à un bus (prosumer)."""
    id: str
    bus_id: str
    profile: np.ndarray
    def series(self, t: np.ndarray) -> np.ndarray:
        return np.asarray(self.profile, dtype=float)

@dataclass
class Converter:
    """Converter générique: from_bus --(η)--> to_bus (inverse statique)."""
    id: str
    from_bus: str
    to_bus: str
    eta: float
    # logs
    p_out_W: np.ndarray = field(default=None, init=False)  # injection effectuée sur to_bus
    p_in_W:  np.ndarray = field(default=None, init=False)  # retrait appliqué sur from_bus

# --------------- Runner / Orchestrator ---------------
@dataclass
class InverseStaticDAG:
    t: np.ndarray
    buses: Dict[str, Bus]
    inputs: List[SignedInput]
    converters: Dict[str, Converter]
    dag: nx.DiGraph  # nœuds: bus_id ; arêtes: to_bus -> from_bus (propagation aval)

    @classmethod
    def from_yaml(cls, cfg: dict, t: np.ndarray) -> "InverseStaticDAG":
        # 1) Buses
        buses: Dict[str, Bus] = {}
        for b in cfg["buses"]:
            buses[b["id"]] = Bus(id=b["id"], carrier=b["carrier"], net_W=np.zeros_like(t, dtype=float))

        # 2) Inputs
        inputs: List[SignedInput] = []
        for s in cfg["inputs"]:
            # profil constant ou liste explicite
            if "profile_W" in s:
                prof = np.array(s["profile_W"], dtype=float)
            else:
                prof = np.full_like(t, fill_value=float(s.get("p_const_W", 0.0)), dtype=float)
            inputs.append(SignedInput(id=s["id"], bus_id=s["bus"], profile=prof))

        # 3) Converters
        converters: Dict[str, Converter] = {}
        for c in cfg["converters"]:
            converters[c["id"]] = Converter(
                id=c["id"],
                from_bus=c["from_bus"],
                to_bus=c["to_bus"],
                eta=float(c["eta"]),
            )

        # 4) DAG (bus → bus) pour ordre amont
        # On veut propager des demandes de "to_bus" vers "from_bus"
        dag = nx.DiGraph()
        for bus_id in buses.keys():
            dag.add_node(bus_id)
        for c in converters.values():
            # arête dirigée: (to_bus) -> (from_bus)  (propagation amont)
            dag.add_edge(c.to_bus, c.from_bus, conv_id=c.id)

        # Vérifie l'acyclicité
        if not nx.is_directed_acyclic_graph(dag):
            cycles = list(nx.simple_cycles(dag))
            raise ValueError(f"Graphe non acyclique, cycles trouvés: {cycles}")

        return cls(t=t, buses=buses, inputs=inputs, converters=converters, dag=dag)

    def apply_inputs(self):
        # reset
        for b in self.buses.values():
            b.net_W[:] = 0.0
            b.ledger.clear()
        # inputs
        for s in self.inputs:
            self.buses[s.bus_id].add(label=f"input:{s.id}", series_W=s.series(self.t))

    def run(self):
        """
        Algorithme:
          1) Appliquer les inputs signés sur chaque bus (somme).
          2) Parcourir les bus en ORDRE TOPOLOGIQUE INVERSE (des avals vers les amonts).
             Pour chaque arête (to -> from), on lit le net du 'to_bus':
               - si net < 0 (demande), on injecte p_out = -net sur to_bus via ce convertisseur
                 et on retire p_in = p_out/η du from_bus.
               - si net >= 0, on ne fait rien avec ce convertisseur (pas besoin d'injecter).
             NB : s'il y a plusieurs convertisseurs alimentant le même to_bus, chacun verra le
             net restant (après ceux déjà passés), ce qui permet de partager (ici par priorité d'ordre).
        """
        self.apply_inputs()
        # parcours des bus: ordre topo inverse sur le graphe de buses
        for to_bus in reversed(list(nx.topological_sort(self.dag))):
            # pour chaque arête sortante (to_bus -> from_bus), récupérer le convertisseur
            for _, from_bus, data in self.dag.out_edges(to_bus, data=True):
                conv = self.converters[data["conv_id"]]
                b_to = self.buses[to_bus]
                b_fr = self.buses[from_bus]
                # besoin actuel sur le bus aval (demande = négatif)
                need = -np.minimum(0.0, b_to.net_W)  # vecteur ≥ 0
                if np.any(need > 0.0):
                    p_out = need
                    p_in  = np.divide(p_out, max(conv.eta, 1e-12))
                    # journal
                    conv.p_out_W = p_out.copy()
                    conv.p_in_W  = p_in.copy()
                    # appliquer: injection sur to_bus (+), retrait sur from_bus (−)
                    b_to.add(label=f"from:{conv.id}", series_W=p_out)   # injecte
                    b_fr.add(label=f"to:{conv.id}",   series_W=-p_in)   # retire
                else:
                    # pas de besoin, rien à faire sur cette arête
                    pass

    # utilitaire debug
    def snapshot(self, every: int = 10):
        print("\n=== BUSES (net + ledger) ===")
        for bid, b in self.buses.items():
            print(f"\n[Bus {bid}] carrier={b.carrier}")
            print(f"  net_W sample: {b.net_W[0:len(b.net_W):every][:5]}")
            for k, v in b.ledger.items():
                print(f"  {k:18s} sample: {v[0:len(v):every][:5]}")
        print("\n=== CONVERTERS (pin/pout) ===")
        for cid, c in self.converters.items():
            if c.p_out_W is None:
                print(f"  {cid}: (no action)")
            else:
                print(f"  {cid}: pout→{c.to_bus}  pin←{c.from_bus}  "
                      f"pout[0]={c.p_out_W[0]:.1f}W  pin[0]={c.p_in_W[0]:.1f}W")


# ----------------- Demo -----------------
if __name__ == "__main__":
    # horizon (vectoriel)
    dt = 1.0
    T  = 20
    t  = np.arange(0.0, T*dt, dt)

    # YAML minimal (tu peux mettre ça dans un .yaml — ici je le charge depuis une string pour la démo)
    cfg_txt = """
buses:
  - {id: "Mechanical:shaft", carrier: "Mechanical"}
  - {id: "Electrical:main",  carrier: "Electrical"}
  - {id: "Chemical:fuel",    carrier: "Chemical"}

inputs:
  # v(t)->P_shaft(t) a déjà été transformé en W ici : on met directement la charge méca signée
  - id: "shaft_load"
    bus: "Mechanical:shaft"
    # demande constante: -150 kW
    p_const_W: -150000.0

  # NavOps électrique (demande) : -20 kW
  - id: "hotel"
    bus: "Electrical:main"
    p_const_W: -20000.0

converters:
  # MotorInverse: Elec -> Méca (pour injecter sur Méca, on retire à Elec)
  - {id: "motor_inv",   from_bus: "Electrical:main", to_bus: "Mechanical:shaft", eta: 0.85}
  # GensetInverse: Chem -> Elec (pour injecter sur Elec, on retire à Chem)
  - {id: "genset_inv",  from_bus: "Chemical:fuel",   to_bus: "Electrical:main",  eta: 0.45}
"""
    cfg = yaml.safe_load(cfg_txt)

    runner = InverseStaticDAG.from_yaml(cfg, t)
    runner.run()
    runner.snapshot(every=5)

    # Petit résumé “slacks/surplus”
    print("\n=== Résumé par bus (premier point) ===")
    for bid, b in runner.buses.items():
        print(f"{bid:20s} net={b.net_W[0]/1e3:8.1f} kW   "
              f"(>0 surplus, <0 manque)")
