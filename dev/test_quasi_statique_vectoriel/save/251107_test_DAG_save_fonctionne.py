# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Dict, List
import yaml
import numpy as np
import networkx as nx

def plot_nxGraph(G, pos=False, edges=True) -> None:
    """
    tracé d'un graphe G à partir des attributs obligatoire "label" : 
    label pour G.nodes : 
    G.add_node(0,label='A')
    label pour G.edges : 
    G.add_edge(0,1,label='A-B')
    
    Params :
    --------
    G : graphe
    
    pos : option pour un dictionnaire qui contient les positions des différents noeuds
    obtenu à partir de : pos = nx.spring_layout(G)
    par defaut `pos` vaut 'False' et les positions sont calculées dynamiquement ('True' sinon)
    
    edges : option pour affichage des etiquettes sur les aretes
    par defaut `edges` vaut 'True' et l'etiquette et affichée ('False' sinon)
    """
    # Dict de positions des noeuds
    if not pos: 
        pos = nx.spring_layout(G)
    else:
        pass
    # Dict d'etiquette des noeuds
    liste = list(G.nodes(data='label'))
    labels_nodes = {}
    for noeud in liste:
        labels_nodes[noeud[0]]=noeud[1]
    # Dict d'etiquette des aretes
    labels_edges = {}
    if edges: 
        labels_edges = {edge:G.edges[edge]['label'] for edge in G.edges}
    else:
        labels_edges = {edge:'' for edge in G.edges}
    # nodes
    nx.draw_networkx_nodes(G, pos, alpha=0.7)
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
    return None


# --------------- Protocols ---------------
class SupportPowerConverter(Protocol):
    """Convertisseur de puissance, objet physique."""
    id: str
    from_bus: str   # sens physique
    to_bus: str     # sens physique
    p_in_W: np.ndarray    # sens physique
    p_out_W:  np.ndarray  # sens physique
    
    def forward(self, p_in_w: np.ndarray) -> np.ndarray:
        """Physique: from -> to 
        ex: Genset: Chemical->Electrical (P_out = P_in * η_eff)
        """
        ...

    def inverse(self, p_out_w: np.ndarray) -> np.ndarray:
        """Inverse statique: to -> from
        ex: Genset: Electrical->Chemical (P_in = P_out / η_eff)
        """
        ...
    
class SupportPowerInput(Protocol):
    """Profil de puissance signé et lié à un bus."""
    id: str
    bus: str
    profile: np.ndarray # signé (+ injecte, − consomme)

class SupportPowerBus(Protocol):
    """Bus de puissance avec journal des états."""
    id: str
    carrier: str
    net_W: np.ndarray # signé
    ledger: Dict[str, np.ndarray] # registre


# --------------- Core data ---------------
@dataclass
class Bus(SupportPowerBus):
    """Bus de puissance."""
    id: str
    carrier: str
    net_W: np.ndarray = field(default=None)
    ledger: Dict[str, np.ndarray] = field(default_factory=dict)

@dataclass
class SignedInput(SupportPowerInput):
    """Profil de puissance signé et lié à un bus."""
    id: str
    bus: str
    profile: np.ndarray = field(default=None, init=False)

@dataclass
class Converter(SupportPowerConverter):
    """Convertiseur de puissance générique et lié à deux bus, au sens physique.
    amont->from et aval->to
    La conversion de puissance est faite via un rendement constant.
    """
    id: str
    from_bus: str
    to_bus: str
    eta: float
    # logs
    p_out_W: np.ndarray = field(default=None, init=False)  # injection effectuée sur to_bus
    p_in_W:  np.ndarray = field(default=None, init=False)  # retrait appliqué sur from_bus
    
@dataclass
class SolverDAG:
    t: np.ndarray
    mode: str # "inverse" ou "forward"
    buses: Dict[str, Bus]
    inputs: Dict[str, SignedInput]
    converters: Dict[str, Converter]
    dag: nx.DiGraph
    topo_sort: List[str]

    @classmethod
    def from_yaml(cls, cfg: dict, t: np.ndarray) -> "SolverDAG":
        """
        Initialisation des composants/objets et du graph.
        
        DAG -> Graphe orienté acyclique :
            - propagation vers l'aval, selon le sens physique
            - nœuds: bus_id
            - arêtes: from_bus -> to_bus (sens des arêtes → toujours physique)
        Affichage du graph (networkx), 
        → il montre les flèches dans le sens du flux réel (physique).
        
        MODE -> mode du solveur, "forward" ou "inverse"
            - En mode "forward" : il suit le graphe dans le sens des arêtes.
            - En mode "inverse" : il le parcourt dans le sens inverse des arêtes.
        """
        # 1) Buses
        buses: Dict[str, Bus] = {}
        for b in cfg["buses"]:
            buses[b["id"]] = Bus(id=b["id"], carrier=b["carrier"], net_W=np.zeros_like(t, dtype=float))
        
        # 2) Inputs
        inputs: Dict[str, SignedInput] = {}
        for s in cfg["inputs"]:
            inputs[s["id"]] = SignedInput(id=s["id"], bus=s["bus"])
        
        # 3) Converters
        converters: Dict[str, Converter] = {}
        for c in cfg["converters"]:
            converters[c["id"]] = Converter(
                id=c["id"],
                from_bus=c["from_bus"],
                to_bus=c["to_bus"],
                eta=float(c["eta"]),
            )

        # 4) DAG, sens physique (les labels uniquement pour affichage)
        dag = nx.DiGraph()
        for bus in buses.values():
            dag.add_node(bus.id, carrier=bus.carrier, label=bus.id)
        for c in converters.values():
            dag.add_edge(c.from_bus, c.to_bus, conv_id=c.id, label=c.id)
        # Vérifie l'acyclicité
        if not nx.is_directed_acyclic_graph(dag):
            cycles = list(nx.simple_cycles(dag))
            raise ValueError(f"Graphe non acyclique, cycles trouvés: {cycles}")
        
        # 5) Modes, sens du calcul et tri topologique
        mode = cfg["solver"]["mode"]
        # Vérifie le mode
        valid_mode = ["forward", "inverse"]
        if mode not in valid_mode:
            raise ValueError(f"Le mode est invalide, mode fourni: {mode}\n"
                             f"Modes valides : {valid_mode}")
        # Efféctue le tri topologique sur le DAG, ordre du processus de calcul
        topo_lst = list(nx.topological_sort(dag))
        if mode == "forward":
            topo_sort = topo_lst.copy()
        elif mode == "inverse":
            topo_sort = list(reversed(topo_lst))
        else:
            NotImplementedError(f"L'ordre spécifique du mode {mode} n'est pas implémenté.")
        
        return cls(
            t=t, 
            mode=mode, 
            buses=buses, 
            inputs=inputs, 
            converters=converters, 
            dag=dag, 
            topo_sort=topo_sort
        )
        
        
if __name__ == "__main__":
    # horizon (vectoriel)
    dt = 1.0
    T  = 20
    t  = np.arange(0.0, T*dt, dt)
    
    # YAML minimal
    cfg_txt = """
solver:
  mode: "inverse"   # ou "forward"
  
buses:
  - {id: "Mechanical:shaft", carrier: "Mechanical"}
  - {id: "Electrical:main",  carrier: "Electrical"}
  - {id: "Chemical:fuel",    carrier: "Chemical"}

inputs:
  - {id: "shaft_demand", bus: "Mechanical:shaft"}  # demande méca
  - {id: "navops",       bus: "Electrical:main"}   # demande élec

converters:
  - id: "genset"
    from_bus: "Chemical:fuel"       # physique (amont)
    to_bus:   "Electrical:main"     # physique (aval)
    eta:  0.45

  - id: "motor"
    from_bus: "Electrical:main"
    to_bus:   "Mechanical:shaft"
    eta:  0.9
"""
    cfg = yaml.safe_load(cfg_txt)
    
    solver = SolverDAG.from_yaml(cfg, t)
    
    plot_nxGraph(solver.dag)
