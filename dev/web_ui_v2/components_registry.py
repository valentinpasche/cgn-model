"""Registry et helpers de gestion composants UI V2."""

from __future__ import annotations

import re
from typing import Any

from dash import html
from dash_pydantic_form import ModelForm, fields
from pydantic import BaseModel

from components_basemodel import (
    COURSES_NUMBER,
    ConstantProfile,
    ConstantEtaConverter,
    FileProfile,
    ForceAndSpeedToPowerAdapter,
    NavSpeedProfile,
    SeriesProfile,
    StorageGeneric,
    SpeedToForcePoly,
    SpeedToPowerPolyAdapter,
    VariableEtaConverter,
)
from services.storage import list_schemas, list_templates


TYPE_OPTIONS = [
    {"label": "Profil (signal entree)", "value": "profile"},
    {"label": "Adaptateur (transformateur signal)", "value": "adapter"},
    {"label": "Convertisseur puissance (watt)", "value": "converter"},
    {"label": "Stockage energie", "value": "storage"},
]

AIO_ID = "v2m-form"
FORM_ID = "main"

MODEL_SPECS: dict[str, dict[str, Any]] = {
    "profile.nav_speed": {
        "component_type": "profile",
        "kind": "nav_speed",
        "model": NavSpeedProfile,
    },
    "profile.constant": {
        "component_type": "profile",
        "kind": "constant",
        "model": ConstantProfile,
    },
    "profile.file": {
        "component_type": "profile",
        "kind": "file",
        "model": FileProfile,
    },
    "profile.series": {
        "component_type": "profile",
        "kind": "series",
        "model": SeriesProfile,
    },
    "converter.constant_eta": {
        "component_type": "converter",
        "kind": "constant_eta",
        "model": ConstantEtaConverter,
    },
    "converter.variable_eta": {
        "component_type": "converter",
        "kind": "variable_eta",
        "model": VariableEtaConverter,
    },
    "adapter.speed_to_power_poly": {
        "component_type": "adapter",
        "kind": "speed_to_power_poly",
        "model": SpeedToPowerPolyAdapter,
    },
    "adapter.force_and_speed_to_power": {
        "component_type": "adapter",
        "kind": "force_and_speed_to_power",
        "model": ForceAndSpeedToPowerAdapter,
    },
    "adapter.speed_to_force_poly": {
        "component_type": "adapter",
        "kind": "speed_to_force_poly",
        "model": SpeedToForcePoly,
    },
    "storage.generic": {
        "component_type": "storage",
        "kind": "generic",
        "model": StorageGeneric,
    },
}


def first_doc_line(model_cls: type[BaseModel]) -> str:
    lines = (model_cls.__doc__ or "").strip().splitlines()
    return lines[0].strip() if lines else model_cls.__name__


def model_options(component_type: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for key, spec in MODEL_SPECS.items():
        if spec["component_type"] == component_type:
            out.append({"label": first_doc_line(spec["model"]), "value": key})
    return out


def default_model_key(component_type: str) -> str | None:
    opts = model_options(component_type)
    if not opts:
        return None
    return str(opts[0]["value"])


def _course_options_for_cruise(cruise_name: str | None) -> list[dict[str, str]]:
    if cruise_name and cruise_name in COURSES_NUMBER:
        values = COURSES_NUMBER[cruise_name]
    else:
        values = sorted({n for course_list in COURSES_NUMBER.values() for n in course_list})
    return [{"value": str(n), "label": str(n)} for n in values]


def fields_repr(model_key: str | None, seed: dict[str, Any] | None = None) -> dict[str, Any]:
    if model_key in {"adapter.speed_to_power_poly", "adapter.speed_to_force_poly"}:
        return {
            "coeffs": fields.List(
                render_type="scalar",
                n_cols="var(--pydf-form-cols)",
                wrapper_kwargs={"style": {"gridTemplateColumns": "repeat(5, minmax(0, 1fr))"}},
            )
        }
    if model_key == "profile.nav_speed":
        cruise_name = None
        select_mode = "cruise"
        if isinstance(seed, dict):
            cruise_name = seed.get("cruise_name")
            select_mode = str(seed.get("select", "cruise"))
        # Important: en mode "cruise", on ne surcharge pas le field_repr.
        # Sinon l'override peut neutraliser la règle `visible` définie dans le modèle.
        if select_mode == "course":
            return {
                "course_no": fields.Select(data=_course_options_for_cruise(str(cruise_name) if cruise_name else None))
            }
        return {}
    return {}


def render_form(model_key: str | None, seed: dict[str, Any] | None):
    if not model_key or model_key not in MODEL_SPECS:
        return html.Div("Aucun modele pour ce type.")
    model_cls = MODEL_SPECS[model_key]["model"]
    item: Any = model_cls
    if isinstance(seed, dict) and seed:
        try:
            item = model_cls.model_validate(seed)
        except Exception:  # noqa: BLE001
            safe_seed = {k: v for k, v in seed.items() if k in model_cls.model_fields}
            item = model_cls.model_construct(**safe_seed)
    return ModelForm(item, AIO_ID, FORM_ID, debounce=200, form_cols=10, fields_repr=fields_repr(model_key, seed))


def validate_form_data(model_key: str, form_data: dict[str, Any]) -> dict[str, Any]:
    model_cls = MODEL_SPECS[model_key]["model"]
    return model_cls.model_validate(form_data).model_dump(exclude_none=True)


def payload_from_data(model_key: str, raw: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    spec = MODEL_SPECS[model_key]
    ctype = str(spec["component_type"])
    kind = str(spec["kind"])

    if model_key == "profile.constant":
        component = {
            "id": raw["id"],
            "kind": kind,
            "unit": raw.get("unit", ""),
            "value": raw.get("value"),
        }
    elif model_key == "profile.series":
        component = {
            "id": raw["id"],
            "kind": kind,
            "unit": raw.get("unit", ""),
            "data": raw.get("data", []),
        }
    elif model_key == "profile.file":
        component = {
            "id": raw["id"],
            "kind": kind,
            "unit": raw.get("unit", ""),
            "file": raw.get("file", ""),
            "column": raw.get("column"),
            "sep": raw.get("sep"),
            "decimal": raw.get("decimal", "."),
        }
    elif model_key == "profile.nav_speed":
        select_mode = str(raw.get("select", "cruise"))
        select_payload: dict[str, Any]
        if select_mode == "course":
            course_raw = raw.get("course_no")
            course_no = None
            if course_raw is not None and str(course_raw).strip():
                course_no = int(str(course_raw))
            select_payload = {
                "by": "course",
                "course_no": course_no,
            }
        else:
            select_payload = {
                "by": "cruise",
                "cruise_name": raw.get("cruise_name"),
            }

        params_raw = raw.get("params", {}) if isinstance(raw.get("params"), dict) else {}

        def _q(obj: Any, unit_fallback: str) -> float | None:
            if isinstance(obj, dict):
                try:
                    return float(obj.get("value"))
                except Exception:  # noqa: BLE001
                    return None
            if obj is None:
                return None
            try:
                return float(obj)
            except Exception:  # noqa: BLE001
                return None

        component = {
            "id": raw["id"],
            "kind": kind,
            "unit": "m/s",
            "source": "cgn_croisieres/all",
            "select": select_payload,
            "params": {
                "acc": _q(params_raw.get("acc"), "m*s^-2"),
                "dec": _q(params_raw.get("dec"), "m*s^-2"),
                "v_croisiere": _q(params_raw.get("v_croisiere"), "m/s"),
                "allow_delay": bool(params_raw.get("allow_delay", True)),
            },
        }
    elif model_key == "converter.constant_eta":
        component = {
            "id": raw["id"],
            "kind": kind,
            "from_bus": raw.get("from_bus"),
            "to_bus": raw.get("to_bus"),
            "params": {"eta": raw["eta"]},
        }
    elif model_key == "converter.variable_eta":
        component = {
            "id": raw["id"],
            "kind": kind,
            "from_bus": raw.get("from_bus"),
            "to_bus": raw.get("to_bus"),
            "params": {"eta_default": 1.0, "eta_source": raw["eta_source"]},
        }
    elif model_key == "adapter.speed_to_power_poly":
        component = {
            "id": raw["id"],
            "kind": kind,
            "source": raw["source"],
            "unit_in": raw.get("unit_in", "m/s"),
            "unit_out": raw.get("unit_out", "W"),
            "params": {"coeffs": raw["coeffs"]},
        }
    elif model_key == "adapter.force_and_speed_to_power":
        component = {
            "id": raw["id"],
            "kind": kind,
            "source": "",
            "unit_in": "",
            "unit_out": raw.get("unit_out", "W"),
            "params": {
                "force_source": raw["force_source"],
                "speed_source": raw["speed_source"],
                "force_unit_in": raw.get("force_unit_in", "N"),
                "speed_unit_in": raw.get("speed_unit_in", "m/s"),
                "clip_min": 0.0,
            },
        }
    elif model_key == "adapter.speed_to_force_poly":
        component = {
            "id": raw["id"],
            "kind": kind,
            "source": raw["source"],
            "unit_in": raw.get("unit_in", "m/s"),
            "unit_out": raw.get("unit_out", "N"),
            "params": {"coeffs": raw["coeffs"]},
        }
    elif model_key == "storage.generic":
        vector_params = raw.get("vector_params")
        if isinstance(vector_params, dict):
            basis = str(vector_params.get("pci_basis", "none"))
            density = vector_params.get("density_kg_m3")

            if basis == "mass" and isinstance(vector_params.get("pci_mass"), dict):
                q = vector_params.get("pci_mass", {})
                vector_params = {
                    "pci_basis": "mass",
                    "pci_value": q.get("value"),
                    "pci_mass_unit": q.get("unit"),
                    "density_kg_m3": density,
                }
            elif basis == "volume" and isinstance(vector_params.get("pci_volume"), dict):
                q = vector_params.get("pci_volume", {})
                vector_params = {
                    "pci_basis": "volume",
                    "pci_value": q.get("value"),
                    "pci_volume_unit": q.get("unit"),
                    "density_kg_m3": density,
                }
            else:
                # support ancien format union (pci_value_unit) et cas "none"
                pci_union = vector_params.get("pci_value_unit")
                if isinstance(pci_union, dict):
                    old_basis = pci_union.get("pci_basis")
                    pci_q = pci_union.get("pci", {})
                    if old_basis == "mass":
                        vector_params = {
                            "pci_basis": "mass",
                            "pci_value": pci_q.get("value"),
                            "pci_mass_unit": pci_q.get("unit"),
                            "density_kg_m3": density,
                        }
                    elif old_basis == "volume":
                        vector_params = {
                            "pci_basis": "volume",
                            "pci_value": pci_q.get("value"),
                            "pci_volume_unit": pci_q.get("unit"),
                            "density_kg_m3": density,
                        }
                    else:
                        vector_params = None
                else:
                    vector_params = None
        has_parameters = bool(raw.get("has_parameters", False))
        component = {
            "id": raw["id"],
            "kind": kind,
            # Champ visible mais auto-genere cote UI, conserve ici pour compat mode debug.
            "bus": raw.get("bus"),
            "vector_energy": raw.get("vector_energy"),
            "vector_params": vector_params if has_parameters else None,
        }
    else:
        raise ValueError(f"Modele non supporte: {model_key}")

    return ctype, kind, {"component": component}


def seed_from_template(component_type: str, kind: str, payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    key = f"{component_type}.{kind}"
    if key not in MODEL_SPECS:
        return None, {}
    c = payload.get("component", {}) if isinstance(payload, dict) else {}
    p = c.get("params", {}) if isinstance(c.get("params"), dict) else {}

    if key == "profile.constant":
        return key, {
            "id": c.get("id", ""),
            "unit": c.get("unit", ""),
            "value": c.get("value"),
        }
    if key == "profile.series":
        return key, {
            "id": c.get("id", ""),
            "unit": c.get("unit", ""),
            "data": c.get("data", []),
        }
    if key == "profile.file":
        return key, {
            "id": c.get("id", ""),
            "unit": c.get("unit", ""),
            "file": c.get("file", ""),
            "column": c.get("column"),
            "sep": c.get("sep"),
            "decimal": c.get("decimal", "."),
        }
    if key == "profile.nav_speed":
        sel = c.get("select", {}) if isinstance(c.get("select"), dict) else {}
        by = str(sel.get("by", "cruise"))
        params = c.get("params", {}) if isinstance(c.get("params"), dict) else {}
        seed = {
            "id": c.get("id", ""),
            "select": "course" if by == "course" else "cruise",
            "cruise_name": sel.get("cruise_name", "Translemanique"),
            "course_no": str(sel.get("course_no")) if sel.get("course_no") is not None else None,
            "params": {
                "acc": {"value": params.get("acc", 0.5), "unit": "m*s^-2"},
                "dec": {"value": params.get("dec", 0.5), "unit": "m*s^-2"},
                "v_croisiere": {"value": params.get("v_croisiere", 7.0), "unit": "m/s"},
                "allow_delay": bool(params.get("allow_delay", True)),
            },
        }
        return key, seed
    if key == "converter.constant_eta":
        return key, {
            "id": c.get("id", ""),
            "from_bus": c.get("from_bus"),
            "to_bus": c.get("to_bus"),
            "eta": p.get("eta", 1.0),
        }
    if key == "converter.variable_eta":
        return key, {
            "id": c.get("id", ""),
            "from_bus": c.get("from_bus"),
            "to_bus": c.get("to_bus"),
            "eta_source": p.get("eta_source", ""),
        }
    if key == "adapter.speed_to_power_poly":
        return key, {
            "id": c.get("id", ""),
            "source": c.get("source", ""),
            "unit_in": c.get("unit_in", "m/s"),
            "unit_out": c.get("unit_out", "W"),
            "coeffs": p.get("coeffs", []),
        }
    if key == "adapter.force_and_speed_to_power":
        return key, {
            "id": c.get("id", ""),
            "force_source": p.get("force_source", ""),
            "speed_source": p.get("speed_source", ""),
            "force_unit_in": p.get("force_unit_in", "N"),
            "speed_unit_in": p.get("speed_unit_in", "m/s"),
            "unit_out": c.get("unit_out", "W"),
        }
    if key == "adapter.speed_to_force_poly":
        return key, {
            "id": c.get("id", ""),
            "source": c.get("source", ""),
            "unit_in": c.get("unit_in", "m/s"),
            "unit_out": c.get("unit_out", "N"),
            "coeffs": p.get("coeffs", []),
        }
    if key == "storage.generic":
        vp = c.get("vector_params")
        basis = "none"
        pci_mass = None
        pci_volume = None
        density = None
        if isinstance(vp, dict):
            basis = str(vp.get("pci_basis", "volume"))
            density = vp.get("density_kg_m3")
            pci_value = vp.get("pci_value")
            if basis == "mass":
                unit = vp.get("pci_mass_unit")
                if pci_value is not None and unit:
                    pci_mass = {"value": pci_value, "unit": unit}
            elif basis == "volume":
                unit = vp.get("pci_volume_unit")
                if pci_value is not None and unit:
                    pci_volume = {"value": pci_value, "unit": unit}
        return key, {
            "id": c.get("id", ""),
            "bus": c.get("bus", "auto-genere"),
            "vector_energy": c.get("vector_energy"),
            "has_parameters": vp is not None,
            "vector_params": {
                "pci_basis": basis,
                "pci_mass": pci_mass,
                "pci_volume": pci_volume,
                "density_kg_m3": density,
            } if vp is not None else {
                "pci_basis": "volume",
                "pci_mass": None,
                "pci_volume": None,
                "density_kg_m3": None,
            },
        }
    return None, {}


def local_rows(local_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(it.get("name", "")),
            "component_type": str(it.get("component_type", "")),
            "kind": str(it.get("kind", "")),
            "status": "local",
            "_scope": "local",
        }
        for it in local_items
    ]


def db_rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in list_templates():
        key = f'{r.get("component_type", "")}.{r.get("kind", "")}'
        if key not in MODEL_SPECS:
            continue
        out.append(
            {
                "name": str(r.get("name", "")),
                "component_type": str(r.get("component_type", "")),
                "kind": str(r.get("kind", "")),
                "status": "DB",
                "_scope": "db",
                "_db_id": int(r.get("id", 0)),
            }
        )
    return out


def mermaid_from_config(config: dict[str, Any] | None) -> str:
    cfg = config if isinstance(config, dict) else {}
    comps = cfg.get("components", [])
    if not isinstance(comps, list):
        return "flowchart LR\n  n0[Configuration vide]"

    allowed_types = {"profile", "adapter", "converter", "storage"}
    nodes_by_name: dict[str, str] = {}
    lines: list[str] = ["flowchart LR"]

    def sanitize(raw: str) -> str:
        cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", raw)
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned or "node"

    def ensure_node(name: str) -> str:
        if name in nodes_by_name:
            return nodes_by_name[name]
        base = sanitize(name)
        node_id = f"n_{base}"
        idx = 1
        while node_id in nodes_by_name.values():
            idx += 1
            node_id = f"n_{base}_{idx}"
        nodes_by_name[name] = node_id
        return node_id

    def render_node(node_id: str, label: str, ctype: str) -> str:
        if ctype == "profile":
            return f'  {node_id}[("{label}")]'
        if ctype == "adapter":
            return f'  {node_id}{{{{"{label}"}}}}'
        if ctype == "converter":
            return f'  {node_id}["{label}"]'
        if ctype == "storage":
            return f'  {node_id}((("{label}")))'
        return f'  {node_id}["{label}"]'

    rows: list[dict[str, Any]] = []
    for c in comps:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name", "")).strip()
        ctype = str(c.get("component_type", "")).strip()
        if not name or ctype not in allowed_types:
            continue
        data = c.get("data", {})
        rows.append({"name": name, "ctype": ctype, "data": data if isinstance(data, dict) else {}})
        ensure_node(name)

    if not rows:
        return "flowchart LR\n  n0[Configuration vide]"

    # Noeuds
    for r in rows:
        lines.append(render_node(nodes_by_name[r["name"]], r["name"], r["ctype"]))

    # Liens explicites entre composants (inputs et bus masques).
    edge_lines: list[tuple[str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    valid_names = set(nodes_by_name.keys())

    def add_edge(src_name: str, dst_name: str, edge_kind: str) -> None:
        if src_name not in valid_names or dst_name not in valid_names:
            return
        if src_name == dst_name:
            return
        key = (src_name, dst_name, edge_kind)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge_lines.append((f"  {nodes_by_name[src_name]} --> {nodes_by_name[dst_name]}", edge_kind))

    # 1) Liens de contexte
    for r in rows:
        dst = r["name"]
        ctype = r["ctype"]
        data = r["data"]
        if ctype == "adapter":
            for k in ("source", "force_source", "speed_source"):
                src = str(data.get(k, "")).strip()
                if src:
                    add_edge(src, dst, "context")
        if ctype == "converter":
            eta_src = str((data.get("params", {}) or {}).get("eta_source", "")).strip()
            if eta_src:
                add_edge(eta_src, dst, "context")

    # 2) Liens energetiques via bus implicites (bus non affiches)
    producers_by_bus: dict[str, list[str]] = {}
    consumers_by_bus: dict[str, list[str]] = {}
    storages_by_bus: dict[str, list[str]] = {}

    for r in rows:
        name = r["name"]
        ctype = r["ctype"]
        data = r["data"]
        if ctype == "converter":
            from_bus = str(data.get("from_bus", "")).strip()
            to_bus = str(data.get("to_bus", "")).strip()
            if from_bus:
                consumers_by_bus.setdefault(from_bus, []).append(name)
            if to_bus:
                producers_by_bus.setdefault(to_bus, []).append(name)
        elif ctype == "storage":
            bus = str(data.get("bus", "")).strip()
            if bus:
                storages_by_bus.setdefault(bus, []).append(name)

    all_buses = set(producers_by_bus.keys()) | set(consumers_by_bus.keys()) | set(storages_by_bus.keys())
    for bus in all_buses:
        producers = producers_by_bus.get(bus, [])
        consumers = consumers_by_bus.get(bus, [])
        storages = storages_by_bus.get(bus, [])

        for p in producers:
            for c in consumers:
                add_edge(p, c, "energy")
        for s in storages:
            for c in consumers:
                add_edge(s, c, "context")

    lines.append("")
    energy_link_indexes: list[int] = []
    context_link_indexes: list[int] = []
    for idx, (edge_line, edge_kind) in enumerate(edge_lines):
        lines.append(edge_line)
        if edge_kind == "energy":
            energy_link_indexes.append(idx)
        else:
            context_link_indexes.append(idx)

    lines.append("")
    lines.append("  classDef energyConv fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100;")
    lines.append("  classDef context fill:#f5f5f5,stroke:#9e9e9e,stroke-width:1px,color:#424242;")
    lines.append("  classDef storage fill:#e8f5e9,stroke:#2e7d32,stroke-width:1.6px,color:#1b5e20;")
    lines.append("  classDef profile fill:#ede7f6,stroke:#5e35b1,stroke-width:1.4px,color:#311b92;")

    conv_nodes = [nodes_by_name[r["name"]] for r in rows if r["ctype"] == "converter"]
    context_nodes = [nodes_by_name[r["name"]] for r in rows if r["ctype"] == "adapter"]
    storage_nodes = [nodes_by_name[r["name"]] for r in rows if r["ctype"] == "storage"]
    profile_nodes = [nodes_by_name[r["name"]] for r in rows if r["ctype"] == "profile"]

    if conv_nodes:
        lines.append(f"  class {','.join(conv_nodes)} energyConv;")
    if context_nodes:
        lines.append(f"  class {','.join(context_nodes)} context;")
    if storage_nodes:
        lines.append(f"  class {','.join(storage_nodes)} storage;")
    if profile_nodes:
        lines.append(f"  class {','.join(profile_nodes)} profile;")

    for idx in context_link_indexes:
        lines.append(f"  linkStyle {idx} stroke:#9e9e9e,stroke-width:1.2px,stroke-dasharray:4 3;")
    for idx in energy_link_indexes:
        lines.append(f"  linkStyle {idx} stroke:#1565c0,stroke-width:2.4px;")

    return "\n".join(lines)


def local_config_rows(local_cfgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(c.get("name", "")),
            "n_components": len(c.get("components", []) if isinstance(c.get("components"), list) else []),
            "status": "local",
            "_scope": "local",
        }
        for c in local_cfgs
    ]


def db_config_rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in list_schemas():
        schema = r.get("schema", {})
        n = len(schema.get("components", []) if isinstance(schema, dict) and isinstance(schema.get("components"), list) else [])
        out.append({"name": str(r.get("name", "")), "n_components": n, "status": "DB", "_scope": "db", "_db_id": int(r.get("id", 0))})
    return out
