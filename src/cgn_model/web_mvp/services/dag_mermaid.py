"""
Utilitaires de generation Mermaid depuis un YAML solver.
"""

from __future__ import annotations

import re
from typing import Any


def _sanitize(raw: str) -> str:
    """
    Convertit un identifiant YAML en identifiant Mermaid stable.

    Parameters
    ----------
    raw : str
        Identifiant source.

    Returns
    -------
    str
        Identifiant contenant uniquement lettres, chiffres et underscores.
    """
    cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", raw)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "node"


def _render_node(node_id: str, label: str, shape: str) -> str:
    """
    Rend une ligne Mermaid pour un noeud type.

    Parameters
    ----------
    node_id : str
        Identifiant Mermaid deja sanitize.
    label : str
        Texte affiche dans le noeud.
    shape : str
        Type logique (`profile`, `adapter`, `input`, `bus`, `converter`,
        `storage` ou generique).

    Returns
    -------
    str
        Ligne Mermaid.
    """
    # Mermaid n'accepte pas toujours les labels vides (""), surtout selon la shape.
    # On force un placeholder minimal pour conserver le noeud sans texte lisible.
    safe_label = label if str(label).strip() else " "
    if shape == "profile":
        return f'  {node_id}[("{safe_label}")]'
    if shape == "adapter":
        return f'  {node_id}{{{{"{safe_label}"}}}}'
    if shape == "input":
        return f'  {node_id}{{"{safe_label}"}}'
    if shape == "bus":
        return f'  {node_id}(("{safe_label}"))'
    if shape == "converter":
        return f'  {node_id}["{safe_label}"]'
    if shape == "storage":
        return f'  {node_id}((("{safe_label}")))'
    return f'  {node_id}["{safe_label}"]'


def yaml_to_mermaid(
    cfg: dict[str, Any],
    *,
    show_inputs: bool = True,
    show_input_labels: bool = True,
    show_bus_labels: bool = True,
    flow_direction: str = "LR",
) -> str:
    """
    Genere un diagramme Mermaid `flowchart LR` a partir du YAML complet.

    En cas de reference inconnue, cree un noeud explicite:
    `ERROR: unknown_ref:<id>`.

    Parameters
    ----------
    cfg : dict[str, Any]
        Configuration complète.
    show_input_labels : bool, optional
        Affiche les noms des noeuds `inputs` (par défaut True).
    show_bus_labels : bool, optional
        Affiche les noms des noeuds `buses` (par défaut True).
    show_inputs : bool, optional
        Affiche les noeuds `inputs`. Si False, les liaisons sont compactées en
        `source --> bus` (par défaut True).
    flow_direction : str, optional
        Direction Mermaid du flowchart (`LR`, `TB`, `RL`, `BT`), par défaut `LR`.
    """
    profiles = cfg.get("profiles", []) or []
    adapters = cfg.get("adapters", []) or []
    inputs = cfg.get("inputs", []) or []
    buses = cfg.get("buses", []) or []
    converters = cfg.get("converters", []) or []
    storages = cfg.get("storages", []) or []

    direction = str(flow_direction or "LR").upper().strip()
    if direction not in {"LR", "TB", "RL", "BT"}:
        direction = "LR"
    lines: list[str] = [f"flowchart {direction}"]
    nodes: dict[str, tuple[str, str]] = {}
    alias: dict[str, str] = {}

    def ensure_node(key: str, label: str, shape: str) -> str:
        node_key = key.strip()
        if node_key in alias:
            return alias[node_key]

        base = _sanitize(node_key)
        idx = 1
        node_id = f"n_{base}"
        while node_id in nodes:
            idx += 1
            node_id = f"n_{base}_{idx}"
        alias[node_key] = node_id
        nodes[node_id] = (label, shape)
        return node_id

    def ref_node(ref_id: str) -> str:
        rid = (ref_id or "").strip()
        if rid in alias:
            return alias[rid]
        if not rid:
            return ensure_node("error_missing_ref", "ERROR: unknown_ref:<empty>", "generic")
        return ensure_node(f"error_unknown_ref_{rid}", f"ERROR: unknown_ref:{rid}", "generic")

    for p in profiles:
        pid = str(p.get("id", "unknown_profile"))
        ensure_node(pid, pid, "profile")

    for a in adapters:
        aid = str(a.get("id", "unknown_adapter"))
        ensure_node(aid, aid, "adapter")

    if show_inputs:
        for i in inputs:
            iid = str(i.get("id", "unknown_input"))
            ilabel = iid if show_input_labels else ""
            ensure_node(iid, ilabel, "input")

    for b in buses:
        bid = str(b.get("id", "unknown_bus"))
        blabel = bid if show_bus_labels else ""
        ensure_node(bid, blabel, "bus")

    for c in converters:
        cid = str(c.get("id", "unknown_converter"))
        ensure_node(cid, cid, "converter")

    for s in storages:
        sid = str(s.get("id", "unknown_storage"))
        ensure_node(sid, sid, "storage")

    edge_lines: list[tuple[str, str]] = []

    def add_edge(line: str, edge_kind: str) -> None:
        edge_lines.append((line, edge_kind))

    for a in adapters:
        aid = str(a.get("id", "unknown_adapter"))
        kind = str(a.get("kind", ""))
        a_node = ref_node(aid)
        params = a.get("params", {}) or {}

        if kind == "force_and_speed_to_power":
            force_source = str(params.get("force_source", "")).strip()
            speed_source = str(params.get("speed_source", "")).strip()
            if force_source:
                add_edge(f"  {ref_node(force_source)} --> {a_node}", "context")
            if speed_source:
                add_edge(f"  {ref_node(speed_source)} --> {a_node}", "context")
        else:
            src = str(a.get("source", "")).strip()
            if src:
                add_edge(f"  {ref_node(src)} --> {a_node}", "context")

    for i in inputs:
        iid = str(i.get("id", "unknown_input"))
        src = str(i.get("source", "")).strip()
        bus = str(i.get("bus", "")).strip()
        if show_inputs:
            i_node = ref_node(iid)
            if src:
                add_edge(f"  {ref_node(src)} --> {i_node}", "context")
            if bus:
                add_edge(f"  {i_node} --> {ref_node(bus)}", "context")
        else:
            if src and bus:
                add_edge(f"  {ref_node(src)} --> {ref_node(bus)}", "context")

    for c in converters:
        cid = str(c.get("id", "unknown_converter"))
        from_bus = str(c.get("from_bus", "")).strip()
        to_bus = str(c.get("to_bus", "")).strip()
        c_node = ref_node(cid)
        if from_bus:
            add_edge(f"  {ref_node(from_bus)} --> {c_node}", "energy")
        if to_bus:
            add_edge(f"  {c_node} --> {ref_node(to_bus)}", "energy")

        kind = str(c.get("kind", ""))
        params = c.get("params", {}) or {}
        if kind == "variable_eta":
            eta_source = str(params.get("eta_source", "")).strip()
            if eta_source:
                add_edge(f"  {ref_node(eta_source)} --> {c_node}", "context")

    for s in storages:
        sid = str(s.get("id", "unknown_storage"))
        bus = str(s.get("bus", "")).strip()
        s_node = ref_node(sid)
        if bus:
            add_edge(f"  {s_node} --> {ref_node(bus)}", "context")

    for node_id, (label, shape) in nodes.items():
        lines.append(_render_node(node_id, label, shape))

    lines.append("")

    energy_link_indexes: list[int] = []
    context_link_indexes: list[int] = []
    for idx, (edge_line, edge_kind) in enumerate(edge_lines):
        lines.append(edge_line)
        if edge_kind == "energy":
            energy_link_indexes.append(idx)
        else:
            context_link_indexes.append(idx)

    # Styles visuels pour distinguer le coeur energetique du reste.
    lines.append("")
    lines.append("  classDef energyBus fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1;")
    lines.append("  classDef energyConv fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100;")
    lines.append("  classDef profile fill:#e8f5e9,stroke:#2e7d32,stroke-width:1.8px,color:#1b5e20;")
    lines.append("  classDef storage fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c;")
    lines.append("  classDef context fill:#f5f5f5,stroke:#9e9e9e,stroke-width:1px,color:#424242;")
    lines.append("  classDef error fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#b71c1c;")

    bus_nodes = [node_id for node_id, (_label, shape) in nodes.items() if shape == "bus"]
    conv_nodes = [node_id for node_id, (_label, shape) in nodes.items() if shape == "converter"]
    profile_nodes = [node_id for node_id, (_label, shape) in nodes.items() if shape == "profile"]
    storage_nodes = [node_id for node_id, (_label, shape) in nodes.items() if shape == "storage"]
    context_nodes = [
        node_id
        for node_id, (_label, shape) in nodes.items()
        if shape in ("adapter", "input", "generic")
    ]
    error_nodes = [
        node_id for node_id, (label, _shape) in nodes.items() if label.startswith("ERROR:")
    ]

    if bus_nodes:
        lines.append(f"  class {','.join(bus_nodes)} energyBus;")
    if conv_nodes:
        lines.append(f"  class {','.join(conv_nodes)} energyConv;")
    if profile_nodes:
        lines.append(f"  class {','.join(profile_nodes)} profile;")
    if storage_nodes:
        lines.append(f"  class {','.join(storage_nodes)} storage;")
    if context_nodes:
        lines.append(f"  class {','.join(context_nodes)} context;")
    if error_nodes:
        lines.append(f"  class {','.join(error_nodes)} error;")

    for idx in context_link_indexes:
        lines.append(f"  linkStyle {idx} stroke:#9e9e9e,stroke-width:1.2px,stroke-dasharray:4 3;")
    for idx in energy_link_indexes:
        lines.append(f"  linkStyle {idx} stroke:#1565c0,stroke-width:2.4px;")

    return "\n".join(lines)
