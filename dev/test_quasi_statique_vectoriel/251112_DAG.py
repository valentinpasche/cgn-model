# -*- coding: utf-8 -*-
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, StrictStr, ConfigDict, model_validator, ValidationError

import yaml
import numpy as np
import networkx as nx

from typing import Protocol, runtime_checkable
from typing import Any, Dict, List, Tuple, Literal, Union, Optional, Mapping, Annotated
from numpy.typing import NDArray

type Mode = Literal["forward", "inverse"]

type BusId = str
type ConvId = str
type Edge = Tuple[BusId, BusId]
type PlanItem = Tuple[Edge, ConvId]
type Plan = List[PlanItem]

type Coord = Union[Tuple[float, float], NDArray[np.float64]]
type Pos = Mapping[str, Coord]


class SolverCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Mode

class BusCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    carrier: StrictStr

class ConverterBaseCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    from_bus: StrictStr
    to_bus: StrictStr
    kind: StrictStr  # discriminant

class ConstantEtaCfg(ConverterBaseCfg):
    kind: Literal["constant_eta"]
    eta: float = Field(gt=0, le=1, allow_inf_nan=False)

class PolyCfg(ConverterBaseCfg):
    kind: Literal["poly"]
    coeffs: list[float]  # ex: y = sum(ai * x^i)

# Liste des convertisseurs
ConverterCfg = Annotated[
    Union[
        ConstantEtaCfg,
        PolyCfg,
    ],
    Field(discriminator="kind")
]

class InputCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    bus: StrictStr

class Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    solver: SolverCfg
    buses: List[BusCfg]
    converters: List[ConverterCfg]
    inputs: List[InputCfg]

    @model_validator(mode="after")
    def cross_checks(self):
        bus_ids = {b.id for b in self.buses}

        # références valides
        bad_conv = [c.id for c in self.converters if c.from_bus not in bus_ids or c.to_bus not in bus_ids]
        bad_in   = [i.id for i in self.inputs if i.bus not in bus_ids]
        if bad_conv:
            raise ValueError(f"Convertisseurs référencent des bus inconnus: {bad_conv}")
        if bad_in:
            raise ValueError(f"Inputs référencent des bus inconnus: {bad_in}")

        # unicité des IDs
        def dups(xs):
            from collections import Counter
            return [k for k, v in Counter(xs).items() if v > 1]

        dup = dups([b.id for b in self.buses]) \
            + dups([c.id for c in self.converters]) \
            + dups([i.id for i in self.inputs])

        if dup:
            raise ValueError(f"IDs dupliqués: {dup}")

        return self

# --------------- Protocols ---------------
@runtime_checkable
class SupportPowerBus(Protocol):
    """Bus de puissance avec journal des états."""
    id: str
    carrier: str
    net_w: np.ndarray # signé
    ledger: Dict[str, np.ndarray] # registre

@runtime_checkable
class SupportPowerInput(Protocol):
    """Profil de puissance signé et lié à un bus."""
    id: str
    bus: str
    profile: np.ndarray # signé (+ injecte, − consomme)

# Protocol minimal
@runtime_checkable
class ConverterLike(Protocol):
    "E.G. isinstance(solver.converters['genset'], ConverterLike)"
    id: str
    from_bus: str
    to_bus: str
    def forward(self, p_in_w: np.ndarray) -> np.ndarray: ...
    def inverse(self, p_out_w: np.ndarray) -> np.ndarray: ...
    
# ABC = contrat nominal (impl imposée)
class ConverterABC(ABC):
    id: str
    from_bus: str
    to_bus: str
    
    @abstractmethod
    def forward(self, p_in_w: np.ndarray) -> np.ndarray: ...
    @abstractmethod
    def inverse(self, p_out_w: np.ndarray) -> np.ndarray: ...

# --------------- Core data ---------------
@dataclass
class Bus:
    """Bus de puissance."""
    id: str
    carrier: str
    net_w: np.ndarray = field(default=None)
    ledger: Dict[str, np.ndarray] = field(default_factory=dict)

@dataclass
class SignedInput:
    """Profil de puissance signé et lié à un bus."""
    id: str
    bus: str
    profile: np.ndarray = field(default=None, init=False)

@dataclass
class ConstantEtaConverter(ConverterABC):
    id: str
    from_bus: str
    to_bus: str
    eta: float
    p_in_w: np.ndarray = field(default=None, init=False) # retrait appliqué sur from_bus
    p_out_w: np.ndarray = field(default=None, init=False) # injection effectuée sur to_bus
    def forward(self, p_in_w):  return p_in_w * self.eta
    def inverse(self, p_out_w): return p_out_w / self.eta

@dataclass
class Graphs:
    exec: nx.DiGraph
    view: nx.DiGraph
    def draw_dag(self): raise NotImplementedError("`draw_dag()` must be use from `SolverDAG`")

def _make_converter(c: ConverterCfg) -> ConverterABC:
    if isinstance(c, ConstantEtaCfg):
        return ConstantEtaConverter(id=c.id, from_bus=c.from_bus, to_bus=c.to_bus, eta=c.eta)
    elif isinstance(c, PolyCfg):
        # return PolyConverter(... coeffs=c.coeffs)
        raise NotImplementedError("PolyConverter pas encore implémenté")
    else:
        # garde-fou si un nouveau type arrive sans implémentation
        raise NotImplementedError(f"Type de convertisseur non géré: {type(c).__name__}")

# --------------- Solver ---------------
@dataclass
class SolverDAG:
    mode: Mode # "inverse" ou "forward"
    buses: Dict[str, Bus]
    converters: Dict[str, ConverterABC]
    inputs: Dict[str, SignedInput]
    dag: Graphs
    plan: Plan

    @classmethod
    def from_yaml(cls, cfg: Union[str, Dict[str, Any]]) -> "SolverDAG":
        parsed = cls._parse_cfg(cfg)          # forme normalisée
        cfg_model = cls._validate_cfg(parsed) # Pydantic (types + validations)
        # ensuite, utilise cfg_model dans tes builders :
        buses, converters, inputs = cls._build_objects(cfg_model)
        graphs = cls._build_graphs(buses, converters, inputs)
        plan = cls._build_plan(graphs.exec, cfg_model.solver.mode)
        return cls(
            mode=cfg_model.solver.mode,
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
    def _build_objects(cfg: Cfg,
    ) -> Tuple[Dict[str, Bus], Dict[str, ConverterABC], Dict[str, SignedInput]]:
    
        # 1) Buses
        buses: Dict[str, Bus] = {}
        for b in cfg.buses:
            buses[b.id] = Bus(id=b.id, carrier=b.carrier)
    
        # 2) Converters
        converters: Dict[str, ConverterABC] = {}
        for c in cfg.converters:
            converters[c.id] = _make_converter
    
        # 3) Inputs
        inputs: Dict[str, SignedInput] = {}
        for s in cfg.inputs:
            inputs[s.id] = SignedInput(id=s.id, bus=s.bus)
    
        return (buses, converters, inputs)
    
    @staticmethod
    def _build_graphs(
        buses: Dict[str, Bus],
        converters: Dict[str, ConverterABC],
        inputs: Dict[str, SignedInput],
    ) -> Graphs:
        
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
    def _build_plan(G: nx.DiGraph, mode: Mode) -> Plan:
        """
        Renvoie une liste ordonnée d'arêtes ((u, v), conv_id) à exécuter.
        - mode='forward' : topo puis out_edges(u)
        - mode='inverse' : topo inversé puis in_edges(v)
        """
        # Tri topologique (ordre de calcul)
        order = list(nx.topological_sort(G))
        plan: Plan = []
    
        if mode == "forward":
            for u in order:
                edges = list(G.out_edges(u, data=True))
                # optionnel: trier par priorité (0 par défaut)
                edges.sort(key=lambda e: e[2].get("priority", 0))
                for _, v, data in edges:
                    if not data.get("virtual", False):
                        plan.append(((u, v), data["conv_id"]))
    
        elif mode == "inverse":
            for v in reversed(order):
                edges = list(G.in_edges(v, data=True))
                edges.sort(key=lambda e: e[2].get("priority", 0))
                for u, _, data in edges:
                    if not data.get("virtual", False):
                        plan.append(((u, v), data["conv_id"]))
        else:
            # avec Pydantic + Literal, on ne devrait jamais arriver ici
            raise NotImplementedError(f"L'ordre spécifique du mode {mode!r} n'est pas implémenté.")
    
        return plan

    def draw_dag(self,
         which: Literal["exec","view"] = "view",
         pos: Optional[Pos] = None,
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
        if which not in ("exec", "view"):
            raise ValueError(f"which invalide: {which!r}")
        G = getattr(self.dag, which)  # "exec" ou "view"
        
        # Dict nodes positions
        pos = nx.spring_layout(G) if pos is None else pos
        
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
    
    solver = SolverDAG.from_yaml(cfg)
    solver.draw_dag()
