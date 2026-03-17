"""
Assemblage de schemas "briques" vers configuration YAML solver.
"""

from __future__ import annotations

import copy
from typing import Any

import yaml


SECTION_BY_TYPE = {
    "profile": "profiles",
    "adapter": "adapters",
    "input": "inputs",
    "converter": "converters",
    "storage": "storages",
}


def blank_schema() -> dict[str, Any]:
    return {
        "name": "Schema",
        "vessel_name": "Bateau",
        "vessel_type": "DE",
        "dt": 1.0,
        "instances": [],
    }


def _infer_bus_carrier(bus_id: str) -> str:
    b = bus_id.lower()
    if "fuel" in b or "h2" in b or "diesel" in b or "chemical" in b:
        return "Chemical"
    if "shaft" in b or "mech" in b:
        return "Mechanical"
    return "Electrical"


def _ensure_buses(cfg: dict[str, Any]) -> None:
    existing = {str(b.get("id", "")): b for b in cfg.get("buses", []) if isinstance(b, dict)}
    required: set[str] = set()

    for inp in cfg.get("inputs", []):
        if isinstance(inp, dict):
            bus = str(inp.get("bus", "")).strip()
            if bus:
                required.add(bus)
    for conv in cfg.get("converters", []):
        if isinstance(conv, dict):
            fb = str(conv.get("from_bus", "")).strip()
            tb = str(conv.get("to_bus", "")).strip()
            if fb:
                required.add(fb)
            if tb:
                required.add(tb)
    for stor in cfg.get("storages", []):
        if isinstance(stor, dict):
            bus = str(stor.get("bus", "")).strip()
            if bus:
                required.add(bus)

    buses = cfg.setdefault("buses", [])
    for bid in sorted(required):
        if bid not in existing:
            buses.append({"id": bid, "carrier": _infer_bus_carrier(bid)})
            existing[bid] = buses[-1]


def build_yaml_config_from_schema(schema: dict[str, Any], templates_by_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """
    Convertit un schema UI en configuration YAML complete.
    """
    cfg: dict[str, Any] = {
        "vessel": {
            "name": str(schema.get("vessel_name", "Bateau")),
            "vessel_type": str(schema.get("vessel_type", "DE")),
        },
        "simulation": {"dt": float(schema.get("dt", 1.0))},
        "profiles": [],
        "adapters": [],
        "inputs": [],
        "solver": {"mode": "inverse"},
        "buses": [],
        "converters": [],
        "storages": [],
    }

    for inst in schema.get("instances", []):
        if not isinstance(inst, dict):
            continue
        template_id = int(inst.get("template_id", 0))
        t = templates_by_id.get(template_id)
        if t is None:
            continue
        ctype = str(t.get("component_type", "")).strip()
        section = SECTION_BY_TYPE.get(ctype)
        if section is None:
            continue
        payload = t.get("payload", {})
        component = payload.get("component", payload)
        if not isinstance(component, dict):
            component = {}
        item = copy.deepcopy(component)
        item["id"] = str(inst.get("instance_id", item.get("id", ""))).strip()
        for key in ("source", "bus", "from_bus", "to_bus"):
            val = str(inst.get(key, "") or "").strip()
            if val:
                item[key] = val
        params_patch = inst.get("params_patch", {})
        if isinstance(params_patch, dict) and params_patch:
            base_params = item.get("params", {})
            if not isinstance(base_params, dict):
                base_params = {}
            merged = dict(base_params)
            merged.update(params_patch)
            item["params"] = merged
        cfg[section].append(item)

    _ensure_buses(cfg)
    return cfg


def to_yaml_text(cfg: dict[str, Any]) -> str:
    return yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)


def yaml_to_simple_mermaid(cfg: dict[str, Any]) -> str:
    """
    Mermaid simple pour le schema en cours.
    """
    lines = ["flowchart LR"]
    buses = cfg.get("buses", []) or []
    for b in buses:
        bid = str(b.get("id", "bus"))
        lines.append(f'  b_{bid.replace(":", "_")}(("{bid}"))')
    for conv in cfg.get("converters", []) or []:
        cid = str(conv.get("id", "conv"))
        fb = str(conv.get("from_bus", "")).replace(":", "_")
        tb = str(conv.get("to_bus", "")).replace(":", "_")
        lines.append(f'  b_{fb} --> c_{cid}["{cid}"] --> b_{tb}')
    return "\n".join(lines)
