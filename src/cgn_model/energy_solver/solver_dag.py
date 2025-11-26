# cgn_model/energy_solver/solver_dag.py

"""
SolverDAG — préparation d'une simulation énergétique basée sur un DAG.

RÔLE (pas d'exécution ici) :
- Parse et NORMALISE un YAML (ou dict) de configuration minimal pour le solveur.
- Valide la config (Pydantic) et construit les objets in-memory : buses, inputs, convertisseurs.
- Construit deux graphes NetworkX : 'exec' (exécution) et 'view' (visualisation).
- Génère un 'plan' ordonné d'arêtes à parcourir selon le mode ('forward'/'inverse').
- Fournit un utilitaire d’affichage du DAG.

API PUBLIQUE :
- SolverDAG.from_yaml(cfg: str|dict) -> SolverDAG
    Orchestrateur : parse -> validate -> build_objects -> build_graphs -> build_plan.
- SolverDAG.draw_dag(which='view', pos=None) -> None
    Affiche le graphe 'view' (ou 'exec').

PRIVÉ (helpers internes) :
- _parse_cfg(cfg) -> dict          # ne garde que {solver,buses,inputs,converters}
- _validate_cfg(parsed) -> Cfg      # Pydantic (types + cross-checks)
- _build_objects(cfg_model) -> (buses, converters, inputs)
- _build_graphs(buses, converters, inputs) -> Graphs(exec, view)
- _build_plan(G, mode) -> Plan      # ordre d’exécution des convertisseurs

CONTRATS :
- Ce module NE fait PAS la simulation (vectoriel/stepper). Il prépare la structure.
- _parse_cfg N’ALTÈRE PAS le YAML de départ (pas d’effet de bord).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal
import warnings
import copy

import yaml
import networkx as nx

from cgn_model.energy_solver.types import FArray, Mode, Plan, Pos
from cgn_model.energy_solver.config import Cfg
from cgn_model.energy_solver.components import ConverterABC

__all__ = ["SolverDAG"]

# --- Core data (simples conteneurs) ---
@dataclass
class Bus:
    id: str
    carrier: str
    net_w: FArray | None = field(default=None)
    ledger: dict[str, FArray] = field(default_factory=dict)

@dataclass
class SignedInput:
    id: str
    bus: str
    profile: FArray | None = field(default=None, init=False)

@dataclass
class Graphs:
    exec: nx.DiGraph
    view: nx.DiGraph
    def draw_dag(self): raise NotImplementedError("Use SolverDAG.draw_dag()")

# --- Solver ---
@dataclass
class SolverDAG:
    mode: Mode
    buses: dict[str, Bus]
    converters: dict[str, ConverterABC]
    inputs: dict[str, SignedInput]
    dag: Graphs
    plan: Plan

    # -------- Orchestration --------
    @classmethod
    def from_yaml(cls, cfg: str | dict[str, Any]) -> "SolverDAG":
        parsed = cls._parse_cfg(cfg)          # forme normalisée (+ fallback kind)
        cfg_model = cls._validate_cfg(parsed) # Pydantic
        buses, converters, inputs = cls._build_objects(cfg_model)
        graphs = cls._build_graphs(buses, converters, inputs)
        plan = cls._build_plan(graphs.exec, cfg_model.solver.mode)
        return cls(mode=cfg_model.solver.mode, buses=buses, inputs=inputs, converters=converters, dag=graphs, plan=plan)

    # -------- Parse / Validate --------
    @staticmethod
    def _parse_cfg(cfg: str | dict[str, Any]) -> dict[str, Any]:
        """
        Normalise le YAML d’entrée pour le solveur, **sans modifier l’objet d’origine**.
    
        Entrée
        ------
        cfg : str | dict
            - Chaîne YAML (sera parsée avec yaml.safe_load), OU
            - dictionnaire déjà chargé (p.ex. depuis yaml.safe_load).
    
        Sortie
        ------
        clean : dict[str, Any]
            Dictionnaire **ne contenant que** les 4 sections pertinentes pour le solveur :
            {
              "solver":      dict (vide si absent),
              "buses":       list[dict],    # chaque item est un mapping
              "inputs":      list[dict],
              "converters":  list[dict],    # 'kind' & 'params' normalisés
            }
    
        Garanties & choix de design
        ---------------------------
        - Pas d’effet de bord : l’objet `cfg` d’origine n’est pas modifié.
        - Sections étrangères au solveur (ex. 'meta', 'project', ...) sont ignorées
          dans la valeur de retour, mais **restent** disponibles dans l’objet d’origine
          passé à from_yaml() (pour que l’appelant puisse les consommer ailleurs).
        - 'buses' / 'inputs' / 'converters' sont normalisés en **listes de dicts**.
          Si l’utilisateur a fourni un mapping, il est transformé en liste à 1 élément.
          Si une section est absente ou None, elle devient une liste vide.
        - Hygiène légère : strip() sur quelques champs texte pour éviter les espace/retours.
        - Converters :
            * Fallback : si un convertisseur n’a pas 'kind' mais fournit 'eta',
              on force `kind="constant_eta"` et on migre 'eta' en 'params.eta'.
              Un warning est émis pour informer l’utilisateur.
            * Si 'kind' vaut 'constant_eta' ET qu’un 'eta' top-level traîne,
              on le migre vers 'params.eta'.
        - **Aucune** validation métier avancée ici (cohérence des références bus,
          bornes, etc.) — elles sont faites ensuite par `_validate_cfg` (Pydantic).
    
        Exceptions
        ----------
        - ValueError : si `cfg` n’est pas un mapping YAML valide.
        - TypeError  : si une section attendue n’est ni un mapping ni une liste de mappings.
        - ValueError : si un convertisseur n’a ni 'kind' ni 'eta' (pas de fallback possible).
    
        Exemple
        -------
        >>> raw = {'solver': {'mode':'forward'}, 'buses':[{'id':'A','carrier':'X'}],
                   'converters':[{'id':'c1','from_bus':'A','to_bus':'B','eta':0.9}]}
        >>> clean = _parse_cfg(raw)
        >>> clean['converters'][0]['kind']    # 'constant_eta'
        >>> clean['converters'][0]['params']  # {'eta': 0.9}
        """
        # 1) YAML -> dict si besoin
        source = yaml.safe_load(cfg) if isinstance(cfg, str) else cfg
        if not isinstance(source, dict) or source is None:
            raise ValueError("La configuration YAML est vide ou n'est pas un mapping.")
    
        # 2) Sélection stricte des 4 sections (sans effet de bord)
        solver   = copy.deepcopy(source.get("solver")) if isinstance(source.get("solver"), dict) else {}
        buses_in = source.get("buses")
        inputs_in = source.get("inputs")
        convs_in  = source.get("converters")
    
        # 3) Helper : liste ou dict -> **nouvelle** liste[dict] (copiée)
        def ensure_list(value: Any, section: str) -> list[dict[str, Any]]:
            if value is None:
                return []
            if isinstance(value, list):
                out: list[dict[str, Any]] = []
                for x in value:
                    if not isinstance(x, dict):
                        raise TypeError(f"Section '{section}' doit contenir des mappings (dict).")
                    out.append(copy.deepcopy(x))
                return out
            if isinstance(value, dict):
                return [copy.deepcopy(value)]
            raise TypeError(
                f"Section '{section}' doit être une liste ou un mapping; reçu {type(value).__name__}."
            )
    
        buses = ensure_list(buses_in, "buses")
        inputs = ensure_list(inputs_in, "inputs")
        converters = ensure_list(convs_in, "converters")
    
        # 4) Hygiène légère (strip) — uniquement sur notre copie 'clean'
        def strip_in_place(items: list[dict[str, Any]], keys: list[str]) -> None:
            for item in items:
                for k in keys:
                    if isinstance(item.get(k), str):
                        item[k] = item[k].strip()
    
        if isinstance(solver.get("mode"), str):
            solver["mode"] = solver["mode"].strip()
    
        strip_in_place(buses, ["id", "carrier"])
        strip_in_place(inputs, ["id", "bus"])
        strip_in_place(converters, ["id", "from_bus", "to_bus", "kind"])
    
        # 5) Fallback 'kind' + normalisation 'params' (toujours sur la COPIE)
        for conv in converters:
            kind = conv.get("kind")
            if kind is None:
                # pas de kind : on tente fallback si 'eta' est présent
                if "eta" in conv:
                    conv["kind"] = "constant_eta"
                    conv.setdefault("params", {})
                    conv["params"]["eta"] = conv.pop("eta")
                    warnings.warn(
                        f"Converter '{conv.get('id','<unknown>')}' sans 'kind' → fallback 'constant_eta'.",
                        stacklevel=2,
                    )
                else:
                    raise ValueError(
                        f"Converter '{conv.get('id','<unknown>')}' sans 'kind' ni 'eta'. "
                        "Ajoutez 'kind: constant_eta' (avec 'eta') ou un 'kind' supporté."
                    )
            else:
                # kind présent : si 'eta' top-level traîne, range-le dans params
                if kind == "constant_eta" and "eta" in conv:
                    conv.setdefault("params", {})
                    conv["params"]["eta"] = conv.pop("eta")
    
            # S'assure que 'params' existe (utile pour des kinds sans params)
            conv.setdefault("params", {})
    
        # 6) Retourne UNIQUEMENT les 4 sections pertinentes pour le solveur
        clean: dict[str, Any] = {
            "solver": solver or {},   # dict
            "buses": buses,           # list[dict]
            "inputs": inputs,         # list[dict]
            "converters": converters  # list[dict] (kind/params normalisés)
        }
        return clean

    @staticmethod
    def _validate_cfg(parsed: dict[str, Any]) -> Cfg:
        """
        Valide et type avec Pydantic. Retourne une instance Cfg.
        Lève ValueError avec un message lisible en cas d'erreur.
        """
        from pydantic import ValidationError
        try:
            return Cfg.model_validate(parsed)
        except ValidationError as e:
            lines = []
            for err in e.errors():
                loc = " -> ".join(str(p) for p in err.get("loc", ()))
                msg = err.get("msg", "invalid")
                lines.append(f"- {loc}: {msg}")
            pretty = "\n".join(lines)
            raise ValueError(f"YAML invalide:\n{pretty}") from e

    # -------- Builders --------
    @staticmethod
    def _build_objects(cfg: Cfg
    ) -> tuple[dict[str, Bus], dict[str, ConverterABC], dict[str, SignedInput]]:
        from .components import build_converter_from_cfg  # un seul import stable
        
        # 1) Buses
        buses: dict[str, Bus] = {
            b.id: Bus(id=b.id, carrier=b.carrier) for b in cfg.buses
        }
        # 2) Converters
        converters: dict[str, ConverterABC] = {
            c.id: build_converter_from_cfg(c) for c in cfg.converters
        }
        # 3) Inputs
        inputs: dict[str, SignedInput] = {
            s.id: SignedInput(id=s.id, bus=s.bus) for s in cfg.inputs
        }
        
        return (buses, converters, inputs)

    @staticmethod
    def _build_graphs(
        buses: dict[str, Bus],
        converters: dict[str, ConverterABC],
        inputs: dict[str, SignedInput],
    ) -> Graphs:
        
        G = nx.DiGraph()
        for b in buses.values():
            G.add_node(b.id, carrier=b.carrier, obj_type="bus", label=b.id)
        for c in converters.values():
            G.add_edge(c.from_bus, c.to_bus, conv_id=c.id, obj_type="converter", 
                       label=c.id, virtual=False)
        
        if not nx.is_directed_acyclic_graph(G):
            cycles = list(nx.simple_cycles(G))
            raise ValueError(f"Graphe non acyclique, cycles trouvés: {cycles}")

        V = G.copy()
        for s in inputs.values():
            V.add_node(s.id, obj_type="input", label=s.id)
            V.add_edge(s.id, s.bus, obj_type="input_link", 
                       label=f"{s.id}", virtual=True)
        
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

    # -------- Viz --------
    def draw_dag(
        self, 
        which: Literal["exec","view"] = "view", 
        pos: Pos | None = None
    ) -> None:
        
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

