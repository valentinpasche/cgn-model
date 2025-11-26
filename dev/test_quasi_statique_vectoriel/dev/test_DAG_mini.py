# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict
import yaml
import numpy as np
import networkx as nx


def plot_nxGraph(G, pos=False, edges=True):
    """
    tracé d'un graphe G à partir des options obligatoires : 
    label et col pour G.nodes : 
    G.add_node(0,label='A',col='pink')
    weight et styl pour G.edges :
    G.add_edge(0,1,weight=6,styl='dashed')
    
    Params :
    --------
    G : graphe
    
    pos : option pour un dictionnaire qui contient les positions des différents noeuds
    obtenu à partir de : pos = nx.spring_layout(G)
    
    edges : option pour affichage des etiquettes sur les aretes
    par defaut edges vaut 'True' et l'etiquette EST affichée ('False' sinon)
    """
    # positions for all nodes : 
    # à mettre en parametre pour que chaque graphe ait la même disposition
    if not pos : 
        pos = nx.spring_layout(G)
    else :
        pass
    
    # Dict d'etiquette des noeuds
    liste = list(G.nodes(data='label'))
    labels_nodes = {}
    for noeud in liste:
        labels_nodes[noeud[0]]=noeud[1]
    # Dict d'etiquette des aretes
    labels_edges = {}
    
    if edges : 
        labels_edges = {edge:G.edges[edge]['label'] for edge in G.edges}
    else :
        labels_edges = {edge:'' for edge in G.edges}

    # nodes
    nx.draw_networkx_nodes(G, pos, alpha=0.7)
               
    # labels
    nx.draw_networkx_labels(G, pos, labels=labels_nodes,
                        font_color='black',
                        font_family='sans-serif',
                        font_size=11,
                        )

    # edges
    nx.draw_networkx_edges(G, pos, width=2, arrowsize=15)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=labels_edges,
                                 font_color='red',
                                 font_size=11,
                                 )


# --------------- Core data ---------------
@dataclass
class Bus:
    id: str
    carrier: str
    net_W: np.ndarray  # signé: + injection ; - demande
    ledger: Dict[str, np.ndarray] = field(default_factory=dict)

@dataclass
class SignedInput:
    """Profil signé appliqué à un bus."""
    id: str
    bus: str
    profile: np.ndarray
    def series(self, t: np.ndarray) -> np.ndarray:
        return np.asarray(self.profile, dtype=float)

@dataclass
class Converter:
    """Converter générique: from_bus --(η)--> to_bus."""
    id: str
    from_bus: str
    to_bus: str
    eta: float
    # logs
    p_out_W: np.ndarray = field(default=None, init=False)  # injection effectuée sur to_bus
    p_in_W:  np.ndarray = field(default=None, init=False)  # retrait appliqué sur from_bus



if __name__ == "__main__":
    # horizon (vectoriel)
    dt = 1.0
    T  = 20
    t  = np.arange(0.0, T*dt, dt)

    # YAML minimal
    cfg_txt = """
buses:
  - {id: "Mechanical:shaft", carrier: "Mechanical"}
  - {id: "Electrical:main",  carrier: "Electrical"}
  - {id: "Chemical:fuel",    carrier: "Chemical"}

inputs:
  - {id: "shaft_demand", bus: "Mechanical:shaft", p_const_W: -150000.0} # demande méca
  - {id: "navops",       bus: "Electrical:main",  p_const_W:  -20000.0} # demande élec

converters:
  - {id: "motor_inv",  from_bus: "Electrical:main", to_bus: "Mechanical:shaft", eta: 0.85}
  - {id: "genset_inv", from_bus: "Chemical:fuel",   to_bus: "Electrical:main",  eta: 0.45}
"""
    cfg = yaml.safe_load(cfg_txt)
    
    # 1) Buses
    buses: Dict[str, Bus] = {}
    for b in cfg["buses"]:
        buses[b["id"]] = Bus(id=b["id"], carrier=b["carrier"], net_W=np.zeros_like(t, dtype=float))
    
    # 2) Inputs
    inputs: Dict[str, SignedInput] = {}
    for s in cfg["inputs"]:
        # profil constant ou liste explicite
        if "profile_W" in s:
            prof = np.array(s["profile_W"], dtype=float)
        else:
            prof = np.full_like(t, fill_value=float(s.get("p_const_W", 0.0)), dtype=float)
        inputs[s["id"]] = SignedInput(id=s["id"], bus=s["bus"], profile=prof)
    
    # 3) Converters
    converters: Dict[str, Converter] = {}
    for c in cfg["converters"]:
        converters[c["id"]] = Converter(
            id=c["id"],
            from_bus=c["from_bus"],
            to_bus=c["to_bus"],
            eta=float(c["eta"]),
        )
    
    
    dag = nx.DiGraph()
    for bus in buses.values():
        dag.add_node(bus.id, carrier=bus.carrier, label=bus.id)
    for c in converters.values():
        dag.add_edge(c.from_bus, c.to_bus, conv_id=c.id, label=c.id)
    
    plot_nxGraph(dag)
    
    # Vérifie l'acyclicité
    if not nx.is_directed_acyclic_graph(dag):
        cycles = list(nx.simple_cycles(dag))
        raise ValueError(f"Graphe non acyclique, cycles trouvés: {cycles}")
        
    lst_ordre = list(nx.topological_sort(dag))
    
    
    
