"""
Utilitaires de generation Mermaid depuis un YAML solver.
"""

from __future__ import annotations

import re
from typing import Any


def _sanitize(raw: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", raw)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "node"


def _render_node(node_id: str, label: str, shape: str) -> str:
    if shape == "profile":
        return f'  {node_id}[("{label}")]'
    if shape == "adapter":
        return f'  {node_id}{{{{"{label}"}}}}'
    if shape == "input":
        return f'  {node_id}{{"{label}"}}'
    if shape == "bus":
        return f'  {node_id}(("{label}"))'
    if shape == "converter":
        return f'  {node_id}["{label}"]'
    if shape == "storage":
        return f'  {node_id}((("{label}")))'
    return f'  {node_id}["{label}"]'


def yaml_to_mermaid(cfg: dict[str, Any]) -> str:
    """
    Genere un diagramme Mermaid `flowchart LR` a partir du YAML complet.

    En cas de reference inconnue, cree un noeud explicite:
    `ERROR: unknown_ref:<id>`.
    """
    profiles = cfg.get("profiles", []) or []
    adapters = cfg.get("adapters", []) or []
    inputs = cfg.get("inputs", []) or []
    buses = cfg.get("buses", []) or []
    converters = cfg.get("converters", []) or []
    storages = cfg.get("storages", []) or []

    lines: list[str] = ["flowchart LR"]
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

    for i in inputs:
        iid = str(i.get("id", "unknown_input"))
        ensure_node(iid, iid, "input")

    for b in buses:
        bid = str(b.get("id", "unknown_bus"))
        ensure_node(bid, bid, "bus")

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
        i_node = ref_node(iid)
        if src:
            add_edge(f"  {ref_node(src)} --> {i_node}", "context")
        if bus:
            add_edge(f"  {i_node} --> {ref_node(bus)}", "context")

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
    lines.append("  classDef context fill:#f5f5f5,stroke:#9e9e9e,stroke-width:1px,color:#424242;")
    lines.append("  classDef error fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#b71c1c;")

    bus_nodes = [node_id for node_id, (_label, shape) in nodes.items() if shape == "bus"]
    conv_nodes = [node_id for node_id, (_label, shape) in nodes.items() if shape == "converter"]
    context_nodes = [
        node_id
        for node_id, (_label, shape) in nodes.items()
        if shape in ("profile", "adapter", "input", "storage", "generic")
    ]
    error_nodes = [
        node_id for node_id, (label, _shape) in nodes.items() if label.startswith("ERROR:")
    ]

    if bus_nodes:
        lines.append(f"  class {','.join(bus_nodes)} energyBus;")
    if conv_nodes:
        lines.append(f"  class {','.join(conv_nodes)} energyConv;")
    if context_nodes:
        lines.append(f"  class {','.join(context_nodes)} context;")
    if error_nodes:
        lines.append(f"  class {','.join(error_nodes)} error;")

    for idx in context_link_indexes:
        lines.append(f"  linkStyle {idx} stroke:#9e9e9e,stroke-width:1.2px,stroke-dasharray:4 3;")
    for idx in energy_link_indexes:
        lines.append(f"  linkStyle {idx} stroke:#1565c0,stroke-width:2.4px;")

    return "\n".join(lines)
