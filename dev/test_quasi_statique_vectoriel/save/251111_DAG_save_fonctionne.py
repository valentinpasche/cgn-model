# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Dict, List
import yaml
import numpy as np
import networkx as nx

# --------------- Protocols ---------------
class SupportPowerBus(Protocol):
    """Bus de puissance avec journal des états."""
    id: str
    carrier: str
    net_W: np.ndarray # signé
    ledger: Dict[str, np.ndarray] # registre

class SupportPowerInput(Protocol):
    """Profil de puissance signé et lié à un bus."""
    id: str
    bus: str
    profile: np.ndarray # signé (+ injecte, − consomme)

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
        raise NotImplementedError("forward() must be implemented in subclass")

    def inverse(self, p_out_w: np.ndarray) -> np.ndarray:
        """Inverse statique: to -> from
        ex: Genset: Electrical->Chemical (P_in = P_out / η_eff)
        """
        raise NotImplementedError("inverse() must be implemented in subclass")


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
    dag: Dict[str, nx.DiGraph]
    plan: List[str]
    
    def draw_dag(self, pos=False, exec_dag=False) -> None:
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
        if exec_dag:
            G = self.dag["exec"]
        else:
            G = self.dag["view"]
        
        # Dict nodes positions
        if not pos: 
            pos = nx.spring_layout(G)
        else:
            pass
        
        # nodes buses
        n_bus = [k for k, v in G.nodes(data="obj_type") if v == "bus"]
        nx.draw_networkx_nodes(G, pos, nodelist=n_bus,
            node_size=700,
            node_color="tab:blue",
        )
        # nodes inputs
        n_input = [k for k, v in G.nodes(data="obj_type") if v == "input"]
        nx.draw_networkx_nodes(G, pos, nodelist=n_input,
            node_size=500,
            node_color="tab:green",
        )
        # edges converters
        e_real = [(u, v) for (u, v, d) in G.edges(data=True) if not d["virtual"]]
        nx.draw_networkx_edges(G, pos, edgelist=e_real,
            width=2,
            edge_color="black",
            style="solid",
            arrowsize=15,
        )
        # edges inputs, virtual
        e_virtual = [(u, v) for (u, v, d) in G.edges(data=True) if d["virtual"]]
        nx.draw_networkx_edges(G, pos, edgelist=e_virtual,
            width=2,
            edge_color="black",
            style="dashed",
            arrowsize=15,
        )
        # node labels
        node_labels = nx.get_node_attributes(G, "label")
        nx.draw_networkx_labels(G, pos, node_labels,
            font_color="black",
            font_family="sans-serif",
            font_size=13,
        )
        # edges label
        edge_labels = nx.get_edge_attributes(G, "label")
        step_index = {edge: i for i, (edge, _) in enumerate(self.plan, start=1)}
        edge_labels_step = {
            edge: (f"{label} ({step_index[edge]})" if edge in step_index else f"{label} (in)")
            for edge, label in edge_labels.items()
        }
        nx.draw_networkx_edge_labels(G, pos, edge_labels_step,
            font_color="red",
            font_family="sans-serif",
            font_size=13,
        )
        
        return None    
    
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
        def build_exec_dag(buses: Dict[str, Bus], converters: Dict[str, Converter]) -> nx.DiGraph:
            G = nx.DiGraph()
            # nœuds = buses
            for b in buses.values():
                G.add_node(b.id, carrier=b.carrier, obj_type="bus", label=b.id)
            # arêtes = convertisseurs (physique)
            for c in converters.values():
                G.add_edge(c.from_bus, c.to_bus,
                           conv_id=c.id, obj_type="converter", label=c.id,
                           virtual=False)
            # sanity check DAG
            if not nx.is_directed_acyclic_graph(G):
                cycles = list(nx.simple_cycles(G))
                raise ValueError(f"Graphe non acyclique, cycles trouvés: {cycles}")
            return G
        
        def build_view_dag(exec_dag: nx.DiGraph, inputs: Dict[str, SignedInput]) -> nx.DiGraph:
            V = exec_dag.copy()
            # ajoute inputs comme nœuds + arêtes virtuelles (non utilisées par l’exécution)
            for s in inputs.values():
                V.add_node(s.id, obj_type="input", label=s.id)
                # choix du sens purement visuel :
                # si tu veux distinguer source/charge : teste le signe moyen du profil
                # ici, on relie input -> bus en pointillé
                V.add_edge(s.id, s.bus, label=f"{s.id}", obj_type="input_link",
                           virtual=True)
            return V        
        
        def build_edge_plan(exec_dag: nx.DiGraph, mode: str) -> list[tuple[tuple[str, str], str]]:
            """
            Renvoie une liste ordonnée d'arêtes ((u, v), conv_id) à exécuter.
            - mode='forward' : parcourt topo u puis ses out_edges(u)
            - mode='inverse' : parcourt topo inversé v puis ses in_edges(v)  (on remonte)
            Si tu veux gérer des priorités entre plusieurs convertisseurs vers le même bus,
            stocke un attribut 'priority' sur l'arête et trie localement.
            """        
            
            # Efféctue le tri topologique sur le DAG, ordre du processus de calcul
            order = list(nx.topological_sort(exec_dag))
            plan: List[tuple[tuple[str,str],str]] = []
        
            if mode == "forward":
                for u in order:
                    edges = list(exec_dag.out_edges(u, data=True))
                    # optionnel: trier par priorité
                    edges.sort(key=lambda e: e[2].get("priority", 0), reverse=False)
                    for _, v, data in edges:
                        if not data.get("virtual", False):
                            plan.append(((u, v), data["conv_id"]))
        
            elif mode == "inverse":
                for v in reversed(order):
                    edges = list(exec_dag.in_edges(v, data=True))
                    edges.sort(key=lambda e: e[2].get("priority", 0), reverse=False)
                    for u, _, data in edges:
                        if not data.get("virtual", False):
                            plan.append(((u, v), data["conv_id"]))
            else:
                raise NotImplementedError(f"L'ordre spécifique du mode {mode} n'est pas implémenté.")
        
            return plan

        # 0) Validation du mode d'exectution
        valid_mode = ["forward", "inverse"]
        
        mode = cfg["solver"]["mode"]
        if mode not in valid_mode:
            raise ValueError(f"Le mode est invalide, mode fourni: {mode}\n"
                             f"Modes valides : {valid_mode}")        
        
        # 1) Buses
        buses: Dict[str, Bus] = {}
        for b in cfg["buses"]:
            buses[b["id"]] = Bus(id=b["id"], carrier=b["carrier"], net_W=np.zeros_like(t, dtype=float))
        
        # 2) Converters
        converters: Dict[str, Converter] = {}
        for c in cfg["converters"]:
            converters[c["id"]] = Converter(
                id=c["id"],
                from_bus=c["from_bus"],
                to_bus=c["to_bus"],
                eta=float(c["eta"]),
            )
            
        # 3) Inputs
        inputs: Dict[str, SignedInput] = {}
        for s in cfg["inputs"]:
            inputs[s["id"]] = SignedInput(id=s["id"], bus=s["bus"])

        # 4) DAG et tri topologique
        dag: Dict[str, nx.DiGraph] = {}
        dag["exec"] = build_exec_dag(buses, converters)
        dag["view"] = build_view_dag(dag["exec"], inputs)
        plan = build_edge_plan(dag["exec"], mode)
        
        return cls(
            t=t, 
            mode=mode, 
            buses=buses, 
            inputs=inputs, 
            converters=converters, 
            dag=dag, 
            plan=plan,
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
    
    solver.draw_dag()
