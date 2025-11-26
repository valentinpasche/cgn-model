# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Any, Dict, List, Tuple, Literal, Union, Optional
import yaml
import numpy as np
import networkx as nx

from pydantic import BaseModel, Field, ValidationError, model_validator

class SolverCfg(BaseModel):
    mode: Literal["forward", "inverse"]

class BusCfg(BaseModel):
    id: str
    carrier: str

class ConverterCfg(BaseModel):
    id: str
    from_bus: str
    to_bus: str
    eta: float = Field(gt=0, le=1, allow_inf_nan=False)

class InputCfg(BaseModel):
    id: str
    bus: str

class Cfg(BaseModel):
    solver: SolverCfg
    buses: list[BusCfg]
    converters: list[ConverterCfg]
    inputs: list[InputCfg]

    @model_validator(mode="after")
    def cross_checks(self):
        bus_ids = {b.id for b in self.buses}
        # références bus existantes
        missing_conv = [c.id for c in self.converters if c.from_bus not in bus_ids or c.to_bus not in bus_ids]
        missing_in = [i.id for i in self.inputs if i.bus not in bus_ids]
        if missing_conv:
            raise ValueError(f"Converters inconnus bus: {missing_conv}")
        if missing_in:
            raise ValueError(f"Inputs inconnus bus: {missing_in}")
        # unicité IDs
        def dups(xs): 
            from collections import Counter; return [k for k,v in Counter(xs).items() if v>1]
        dup_ids = dups([b.id for b in self.buses]) + dups([c.id for c in self.converters]) + dups([i.id for i in self.inputs])
        if dup_ids:
            raise ValueError(f"IDs dupliqués: {dup_ids}")
        return self


# --------------- Protocols ---------------
class SupportPowerBus(Protocol):
    """Bus de puissance avec journal des états."""
    id: str
    carrier: str
    net_w: np.ndarray # signé
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
    p_in_w: np.ndarray    # sens physique
    p_out_w:  np.ndarray  # sens physique
    
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
    net_w: np.ndarray = field(default=None)
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
    p_out_w: np.ndarray = field(default=None, init=False)  # injection effectuée sur to_bus
    p_in_w:  np.ndarray = field(default=None, init=False)  # retrait appliqué sur from_bus

@dataclass
class Graphs:
    exec: nx.DiGraph
    view: nx.DiGraph
    
    def draw_dag(self):
        raise NotImplementedError("`draw_dag()` must be use from `SolverDAG`")

@dataclass
class SolverDAG:
    t: np.ndarray
    mode: str # "inverse" ou "forward"
    buses: Dict[str, Bus]
    inputs: Dict[str, SignedInput]
    converters: Dict[str, Converter]
    dag: Graphs
    plan: List[str]

    @classmethod
    def from_yaml(cls, cfg: dict | str, t: np.ndarray) -> "SolverDAG":
        parsed = cls._parse_cfg(cfg)          # forme normalisée
        cfg_model = cls._validate_cfg(parsed) # Pydantic (types + validations)
        # ensuite, utilise cfg_model dans tes builders :
        buses, converters, inputs = cls._build_objects(t, cfg_model)
        graphs = cls._build_graphs(buses, converters, inputs)
        plan = cls._build_plan(graphs.exec, cfg_model.solver.mode)
        return cls(
            t=t, mode=cfg_model.solver.mode,
            buses=buses, inputs=inputs, converters=converters,
            dag=graphs, plan=plan,
        )

    @staticmethod
    def _parse_cfg(cfg: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Accepte un dict ou une chaîne YAML.
        Normalise la structure attendue par les modèles Pydantic :
          - clés top-level présentes
          - sections 'buses'/'inputs'/'converters' sous forme de listes
          - éléments de liste = dict
        Ne fait pas de validation métier (références, bornes, etc.).
        """
        # 1) YAML -> dict si besoin
        if isinstance(cfg, str):
            cfg = yaml.safe_load(cfg)

        if not isinstance(cfg, dict) or cfg is None:
            raise ValueError("La configuration YAML est vide ou n'est pas un mapping.")

        # 2) Clés top-level manquantes -> valeurs par défaut
        cfg.setdefault("solver", {})
        cfg.setdefault("buses", [])
        cfg.setdefault("inputs", [])
        cfg.setdefault("converters", [])

        # 3) Helper : liste ou dict -> liste
        def ensure_list(value, section: str) -> List[Dict[str, Any]]:
            if value is None:
                return []
            if isinstance(value, list):
                # vérifie que chaque item est un mapping
                if not all(isinstance(x, dict) for x in value):
                    raise TypeError(f"Section '{section}' doit contenir des mappings (dict).")
                return value
            if isinstance(value, dict):
                return [value]
            raise TypeError(
                f"Section '{section}' doit être une liste ou un mapping; reçu {type(value).__name__}."
            )

        cfg["buses"] = ensure_list(cfg.get("buses"), "buses")
        cfg["inputs"] = ensure_list(cfg.get("inputs"), "inputs")
        cfg["converters"] = ensure_list(cfg.get("converters"), "converters")

        # 4) Optionnel : strip basique sur quelques champs connus (hygiene légère)
        def strip_in_place(items: List[Dict[str, Any]], keys: List[str]) -> None:
            for item in items:
                for k in keys:
                    if isinstance(item.get(k), str):
                        item[k] = item[k].strip()

        if isinstance(cfg.get("solver"), dict) and isinstance(cfg["solver"].get("mode"), str):
            cfg["solver"]["mode"] = cfg["solver"]["mode"].strip()

        strip_in_place(cfg["buses"], ["id", "carrier"])
        strip_in_place(cfg["inputs"], ["id", "bus"])
        strip_in_place(cfg["converters"], ["id", "from_bus", "to_bus"])

        return cfg

    @staticmethod
    def _validate_cfg(parsed: Dict[str, Any]) -> "Cfg":
        """
        Valide et typpe avec Pydantic. Retourne une instance Cfg.
        Lève ValueError avec un message lisible en cas d'erreur.
        """
        try:
            return Cfg.model_validate(parsed)
        except ValidationError as e:
            # Message lisible
            lines = []
            for err in e.errors():
                loc = " -> ".join(str(p) for p in err.get("loc", ()))
                msg = err.get("msg", "invalid")
                lines.append(f"- {loc}: {msg}")
            pretty = "\n".join(lines)
            raise ValueError(f"YAML invalide:\n{pretty}") from e
    
    @staticmethod
    def _build_objects(t, parsed) -> Tuple[Dict[str, Bus], Dict[str, Converter], Dict[str, SignedInput]]:
        
        # 1) Buses
        buses: Dict[str, Bus] = {}
        for b in cfg["buses"]:
            buses[b["id"]] = Bus(id=b["id"], carrier=b["carrier"], net_w=np.zeros_like(t, dtype=float))
        
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

        return (buses, converters, inputs)
    
    @staticmethod
    def _build_graphs(
        buses: Dict[str, Bus],
        converters: Dict[str, Bus],
        inputs: Dict[str, Converter],
    ) -> Tuple[Dict[str, nx.DiGraph]]:
        
        # Graph de simulation, plan de calcul
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
        
        # Graph de visualisation, avec les inputs
        V = G.copy()
        # ajoute inputs comme nœuds + arêtes virtuelles (non utilisées par l’exécution)
        for s in inputs.values():
            V.add_node(s.id, obj_type="input", label=s.id)
            # choix du sens purement visuel :
            # si tu veux distinguer source/charge : teste le signe moyen du profil
            # ici, on relie input -> bus en pointillé
            V.add_edge(s.id, s.bus, label=f"{s.id}", obj_type="input_link",
                       virtual=True)
        
        return Graphs(exec=G, view=V)
    
    @staticmethod
    def _build_plan(G: nx.DiGraph, mode: str) -> List[Tuple[Tuple[str, str], str]]:
            """
            Renvoie une liste ordonnée d'arêtes ((u, v), conv_id) à exécuter.
            - mode='forward' : parcourt topo u puis ses out_edges(u)
            - mode='inverse' : parcourt topo inversé v puis ses in_edges(v)  (on remonte)
            Si tu veux gérer des priorités entre plusieurs convertisseurs vers le même bus,
            stocke un attribut 'priority' sur l'arête et trie localement.
            """        
            
            # Efféctue le tri topologique sur le DAG, ordre du processus de calcul
            order = list(nx.topological_sort(G))
            plan: List[Tuple[Tuple[str, str], str]] = []
        
            if mode == "forward":
                for u in order:
                    edges = list(G.out_edges(u, data=True))
                    # optionnel: trier par priorité
                    edges.sort(key=lambda e: e[2].get("priority", 0), reverse=False)
                    for _, v, data in edges:
                        if not data.get("virtual", False):
                            plan.append(((u, v), data["conv_id"]))
        
            elif mode == "inverse":
                for v in reversed(order):
                    edges = list(G.in_edges(v, data=True))
                    edges.sort(key=lambda e: e[2].get("priority", 0), reverse=False)
                    for u, _, data in edges:
                        if not data.get("virtual", False):
                            plan.append(((u, v), data["conv_id"]))
            else:
                raise NotImplementedError(f"L'ordre spécifique du mode {mode} n'est pas implémenté.")
        
            return plan



    def draw_dag(self,
         which: Literal["exec","view"] = "view",
         pos: Optional[Dict[str, tuple[float, float]]] = None,
     ) -> None:
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
        par defaut `pos` vaut 'None' et les positions sont calculées dynamiquement.
        """
        G = getattr(self.dag, which)  # "exec" ou "view"
        if not hasattr(self.dag, which):
            raise ValueError(f"which invalide: {which!r}")
        
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
