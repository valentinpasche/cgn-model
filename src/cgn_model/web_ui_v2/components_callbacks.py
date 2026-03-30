"""Callbacks UI V2 composants (DB-only)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
import unicodedata
import yaml
import pandas as pd
import plotly.graph_objects as go

from dash import Input, Output, State, dcc, html, no_update
from dash_pydantic_form import ModelForm
from pydantic import ValidationError

from cgn_model.web_mvp.services.dag_mermaid import yaml_to_mermaid
from cgn_model.web_mvp.services.simulation import run_simulation_from_yaml
from cgn_model.web_ui_v2.components_basemodel import COURSES_NUMBER
from cgn_model.web_ui_v2.components_registry import (
    AIO_ID,
    FORM_ID,
    SCHEMA_AIO_ID,
    SCHEMA_FORM_ID,
    db_rows,
    default_model_key,
    model_options,
    payload_from_data,
    render_form,
    render_schema_form,
    seed_from_template,
    validate_form_data,
)
from cgn_model.web_ui_v2.services.storage import (
    delete_schema,
    delete_template,
    get_template_by_name,
    list_schemas,
    upsert_schema,
    upsert_template,
)


def _is_auto_text(raw: Any) -> bool:
    if not isinstance(raw, str):
        return False
    v = raw.strip().lower()
    v_ascii = (
        unicodedata.normalize("NFKD", v)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    v_ascii = re.sub(r"[^a-z0-9]+", "-", v_ascii).strip("-")
    return (
        v_ascii == "auto"
        or v_ascii.startswith("auto-")
        or "auto-genere" in v_ascii
        or "auto-generate" in v_ascii
        or "auto-generated" in v_ascii
    )


def _schema_components_list(schema_like: dict[str, Any] | None) -> list[str]:
    if not isinstance(schema_like, dict):
        return []
    raw = schema_like.get("components", [])
    out: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                name = str(item.get("name", "") or item.get("id", "")).strip()
                if name:
                    out.append(name)
    uniq: list[str] = []
    seen: set[str] = set()
    for n in out:
        if n not in seen:
            uniq.append(n)
            seen.add(n)
    return uniq


def _catalog() -> dict[str, dict[str, Any]]:
    return {str(r.get("name", "")): r for r in db_rows() if str(r.get("name", "")).strip()}


def _schema_store(name: str, component_names: list[str], catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    for comp_id in component_names:
        item = catalog.get(comp_id)
        if item is None:
            rows.append({"name": comp_id, "status": "N/A", "model": "N/A"})
            continue
        model = f"{item.get('component_type', '')}.{item.get('kind', '')}"
        t = get_template_by_name(comp_id)
        if isinstance(t, dict):
            mk, _ = seed_from_template(str(t.get("component_type", "")), str(t.get("kind", "")), t.get("payload", {}))
            if mk:
                model = mk
        rows.append({"name": comp_id, "status": "OK", "model": model})
    return {"name": name, "components": rows}


def _schema_db_payload(schema_store: dict[str, Any]) -> dict[str, Any]:
    name = str(schema_store.get("name", "")).strip()
    comps = _schema_components_list(schema_store)
    return {"name": name, "components": comps}


_TARGETED_ADAPTER_KINDS = {
    "speed_to_power_poly",
    "force_and_speed_to_power",
    "power_to_power_poly",
}


def _component_seed_by_name(component_name: str) -> tuple[str, str, dict[str, Any]]:
    t = get_template_by_name(component_name)
    if not isinstance(t, dict):
        return "", "", {}
    ctype = str(t.get("component_type", ""))
    kind = str(t.get("kind", ""))
    _, seed = seed_from_template(ctype, kind, t.get("payload", {}))
    d = seed if isinstance(seed, dict) else {}
    return ctype, kind, d


def _schema_edges(schema_components: list[str]) -> list[tuple[str, str]]:
    names = set(schema_components)
    edges: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for dst in schema_components:
        ctype, kind, d = _component_seed_by_name(dst)
        if not ctype:
            continue

        refs: list[str] = []
        for key in ("source", "force_source", "speed_source", "from_bus", "to_bus", "eta_source"):
            v = str(d.get(key, "")).strip()
            if v:
                refs.append(v)
        params = d.get("params", {})
        if isinstance(params, dict):
            eta_src = str(params.get("eta_source", "")).strip()
            if eta_src:
                refs.append(eta_src)
        # Liaison explicite adaptateur -> convertisseur cible.
        if ctype == "adapter" and kind in _TARGETED_ADAPTER_KINDS:
            target = str(d.get("target", "")).strip()
            if target and target in names and target != dst:
                edge = (dst, target)
                if edge not in seen:
                    seen.add(edge)
                    edges.append(edge)

        for src in refs:
            if src in names and src != dst:
                edge = (src, dst)
                if edge not in seen:
                    seen.add(edge)
                    edges.append(edge)
    return edges


def _schema_to_mermaid(schema_components: list[str], catalog: dict[str, dict[str, Any]]) -> str:
    if not schema_components:
        return (
            "flowchart LR\n"
            "  n0[/Schéma vide/]\n"
            "  classDef error fill:#ffebee,stroke:#c62828,stroke-width:2.4px,stroke-dasharray:8 5,color:#b71c1c,font-size:22px,font-weight:bold;\n"
            "  class n0 error;"
        )

    def sanitize(raw: str) -> str:
        cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", raw)
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned or "node"

    node_ids: dict[str, str] = {}
    lines: list[str] = ["flowchart LR"]
    profile_nodes: list[str] = []
    adapter_nodes: list[str] = []
    converter_nodes: list[str] = []
    storage_nodes: list[str] = []
    generic_nodes: list[str] = []
    unknown_nodes: list[str] = []

    for idx, comp_id in enumerate(schema_components, start=1):
        node_ids[comp_id] = f"n_{sanitize(comp_id)}_{idx}"

    for comp_id in schema_components:
        node_id = node_ids[comp_id]
        item = catalog.get(comp_id)
        if item is None:
            lines.append(f'  {node_id}["ERROR: unknown_ref:{comp_id}"]')
            unknown_nodes.append(node_id)
            continue
        ctype = str(item.get("component_type", ""))
        if ctype == "profile":
            lines.append(f'  {node_id}[("{comp_id}")]')
            profile_nodes.append(node_id)
        elif ctype == "adapter":
            lines.append(f'  {node_id}{{{{"{comp_id}"}}}}')
            adapter_nodes.append(node_id)
        elif ctype == "converter":
            lines.append(f'  {node_id}["{comp_id}"]')
            converter_nodes.append(node_id)
        elif ctype == "storage":
            lines.append(f'  {node_id}((("{comp_id}")))')
            storage_nodes.append(node_id)
        else:
            lines.append(f'  {node_id}["{comp_id}"]')
            generic_nodes.append(node_id)

    for src, dst in _schema_edges(schema_components):
        lines.append(f"  {node_ids[src]} --> {node_ids[dst]}")

    lines.append("")
    lines.append("  classDef energyConv fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100;")
    lines.append("  classDef profile fill:#e8f5e9,stroke:#2e7d32,stroke-width:1.8px,color:#1b5e20;")
    lines.append("  classDef storage fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c;")
    lines.append("  classDef context fill:#f5f5f5,stroke:#9e9e9e,stroke-width:1px,color:#424242;")
    lines.append("  classDef error fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#b71c1c;")

    if converter_nodes:
        lines.append(f"  class {','.join(converter_nodes)} energyConv;")
    if profile_nodes:
        lines.append(f"  class {','.join(profile_nodes)} profile;")
    if storage_nodes:
        lines.append(f"  class {','.join(storage_nodes)} storage;")
    context_nodes = adapter_nodes + generic_nodes
    if context_nodes:
        lines.append(f"  class {','.join(context_nodes)} context;")
    if unknown_nodes:
        lines.append(f"  class {','.join(unknown_nodes)} error;")
    return "\n".join(lines)


def _validate_schema(schema_components: list[str], catalog: dict[str, dict[str, Any]]) -> str:
    if not schema_components:
        return "Validation echec: schema vide."
    missing = [c for c in schema_components if c not in catalog]
    if missing:
        return f"Validation echec: composants manquants -> {', '.join(missing)}"

    # Contrainte UI: target obligatoire et valide pour adaptateurs qui alimentent un convertisseur.
    converter_ids = {
        c for c in schema_components
        if str((catalog.get(c) or {}).get("component_type", "")) == "converter"
    }
    for comp_id in schema_components:
        item = catalog.get(comp_id) or {}
        if str(item.get("component_type", "")) != "adapter":
            continue
        kind = str(item.get("kind", ""))
        if kind not in _TARGETED_ADAPTER_KINDS:
            continue
        _, _, seed = _component_seed_by_name(comp_id)
        target = str(seed.get("target", "")).strip()
        if not target:
            return f"Validation echec: adaptateur '{comp_id}' sans convertisseur cible (target)."
        if target not in converter_ids:
            return (
                f"Validation echec: target '{target}' de l'adaptateur '{comp_id}' "
                "n'est pas un convertisseur present dans le schema."
            )

    # Contrainte UI MVP: plusieurs convertisseurs ne doivent pas alimenter le meme to_bus.
    # (Reste volontairement dans l'UI, pas dans le solver metier.)
    to_bus_map: dict[str, list[str]] = {}
    for comp_id in schema_components:
        t = get_template_by_name(comp_id)
        if not isinstance(t, dict):
            continue
        if str(t.get("component_type", "")) != "converter":
            continue
        _, seed = seed_from_template(
            str(t.get("component_type", "")),
            str(t.get("kind", "")),
            t.get("payload", {}),
        )
        s = seed if isinstance(seed, dict) else {}
        to_bus = str(s.get("to_bus", "")).strip()
        if not to_bus or _is_auto_text(to_bus):
            continue
        to_bus_map.setdefault(to_bus, []).append(comp_id)
    multi_feeders = {bus: ids for bus, ids in to_bus_map.items() if len(ids) > 1}
    if multi_feeders:
        details = ", ".join(f"{bus}: {ids}" for bus, ids in multi_feeders.items())
        return f"Validation echec: plusieurs convertisseurs alimentent le meme to_bus -> {details}"

    incoming = {c: 0 for c in schema_components}
    outgoing = {c: 0 for c in schema_components}
    for src, dst in _schema_edges(schema_components):
        outgoing[src] += 1
        incoming[dst] += 1
    isolated = [c for c in schema_components if incoming[c] == 0 and outgoing[c] == 0]
    if isolated:
        return f"Validation echec: composants isoles -> {', '.join(isolated)}"
    return "Validation OK: schema coherent."


def _check_schema_save_constraints(schema_store: dict[str, Any]) -> tuple[bool, str]:
    comps = _schema_components_list(schema_store)
    if not comps:
        return False, "Sauvegarde refusee: au moins 1 composant est requis."

    catalog = _catalog()
    missing = [c for c in comps if c not in catalog]
    if missing:
        return False, f"Sauvegarde refusee: composants absents de la DB -> {', '.join(missing)}"

    validation_msg = _validate_schema(comps, catalog)
    if not validation_msg.startswith("Validation OK"):
        return False, f"Sauvegarde refusee: {validation_msg}"
    return True, "OK"


def _check_schema_constraints_for_validate(schema_store: dict[str, Any]) -> tuple[bool, str]:
    comps = _schema_components_list(schema_store)
    if not comps:
        return False, "Validation echec: schema vide."
    catalog = _catalog()
    missing = [c for c in comps if c not in catalog]
    if missing:
        return False, f"Validation echec: composants manquants -> {', '.join(missing)}"
    msg = _validate_schema(comps, catalog)
    return (msg.startswith("Validation OK"), msg)


def _build_schema_bundle(current_schema: dict[str, Any]) -> dict[str, Any]:
    schema_name = str(current_schema.get("name", "")).strip()
    component_names = _schema_components_list(current_schema)
    components: list[dict[str, Any]] = []
    for comp_name in component_names:
        t = get_template_by_name(comp_name)
        if not isinstance(t, dict):
            continue
        components.append(
            {
                "name": str(t.get("name", comp_name)),
                "component_type": str(t.get("component_type", "")),
                "kind": str(t.get("kind", "")),
                "payload": t.get("payload", {}),
            }
        )
    return {"schema": {"name": schema_name, "components": component_names}, "components": components}


def _build_bundle_from_current_schema(current_schema: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
    current = current_schema if isinstance(current_schema, dict) else {"name": "", "components": []}
    ok, msg = _check_schema_constraints_for_validate(current)
    if not ok:
        return None, msg
    name = str(current.get("name", "")).strip()
    if not name:
        return None, "Validation echec: nom du schema requis."
    if any(str(r.get("name", "")) == name for r in list_schemas()):
        return _build_schema_bundle(current), f"Attention: le nom '{name}' existe deja."
    return _build_schema_bundle(current), "Validation OK: schema coherent."


def _compile_bundle_to_yaml(bundle: dict[str, Any]) -> dict[str, Any]:
    schema = bundle.get("schema", {}) if isinstance(bundle, dict) else {}
    components = bundle.get("components", []) if isinstance(bundle, dict) else []
    schema_name = str(schema.get("name", "schema_ui_v2")).strip() or "schema_ui_v2"

    def _bus_id(raw: str) -> str:
        b = str(raw).strip()
        if not b:
            return ""
        return b if b.endswith("_bus") else f"{b}_bus"

    def _is_nonempty(raw: Any) -> bool:
        return isinstance(raw, str) and raw.strip() != ""

    def _is_auto_token(raw: Any) -> bool:
        return _is_auto_text(raw)

    out: dict[str, Any] = {
        "vessel": {"name": schema_name, "vessel_type": "undefined"},
        "simulation": {"dt": 1.0},
        "solver": {"mode": "inverse"},
        "profiles": [],
        "adapters": [],
        "inputs": [],
        "buses": [],
        "converters": [],
        "storages": [],
    }

    # Index convertisseurs par id (utile pour l'auto-input depuis adapters target).
    converter_ids: set[str] = set()
    for item in components if isinstance(components, list) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("component_type", "")).strip() != "converter":
            continue
        payload = item.get("payload", {})
        comp = payload.get("component", {}) if isinstance(payload, dict) else {}
        if isinstance(comp, dict) and _is_nonempty(comp.get("id")):
            converter_ids.add(str(comp.get("id")).strip())

    bus_seen: set[str] = set()

    def _add_bus(bus: str) -> None:
        if not bus:
            return
        if bus in bus_seen:
            return
        bus_seen.add(bus)
        out["buses"].append({"id": bus})

    input_seen: set[str] = set()

    def _make_input_id(adapter_id: str, target_id: str) -> str:
        base = f"{adapter_id}__to__{target_id}_in"
        candidate = base
        i = 1
        while candidate in input_seen:
            i += 1
            candidate = f"{base}_{i}"
        input_seen.add(candidate)
        return candidate

    for item in components if isinstance(components, list) else []:
        if not isinstance(item, dict):
            continue
        ctype = str(item.get("component_type", "")).strip()
        payload = item.get("payload", {})
        comp = payload.get("component", {}) if isinstance(payload, dict) else {}
        if not isinstance(comp, dict):
            continue

        if ctype == "profile":
            out["profiles"].append(comp)
        elif ctype == "adapter":
            adapter = dict(comp)
            adapter_id = str(adapter.get("id", "")).strip()
            target = str(adapter.get("target", "")).strip()
            unit_out = str(adapter.get("unit_out", "")).strip()
            target_sign = str(adapter.get("target_sign", "consume")).strip()
            if target_sign not in {"consume", "inject", "as_is"}:
                target_sign = "consume"

            # target n'est pas un champ métier solver: on le retire du YAML final.
            adapter.pop("target", None)
            adapter.pop("target_sign", None)
            out["adapters"].append(adapter)

            # Génération auto d'input uniquement pour adaptateurs puissance.
            if unit_out == "W" and target and target in converter_ids and adapter_id:
                target_bus = _bus_id(target)
                if target_bus:
                    _add_bus(target_bus)
                    out["inputs"].append(
                        {
                            "id": _make_input_id(adapter_id, target),
                            "bus": target_bus,
                            "source": adapter_id,
                            "sign": target_sign,
                        }
                    )
        elif ctype == "converter":
            conv = dict(comp)
            conv_id = str(conv.get("id", "")).strip()
            kind = str(conv.get("kind", "")).strip()
            params = conv.get("params", {})
            if not isinstance(params, dict):
                params = {}
            if kind == "variable_eta":
                params = dict(params)
                params["eta_default"] = 1.0
            conv["params"] = params

            # to_bus auto: toujours base sur id convertisseur.
            to_bus = _bus_id(conv_id)
            conv["to_bus"] = to_bus
            _add_bus(to_bus)

            from_raw = conv.get("from_bus")
            if _is_nonempty(from_raw) and not _is_auto_token(from_raw):
                from_bus = _bus_id(str(from_raw))
            else:
                from_bus = f"{conv_id}_amont" if conv_id else ""
            if from_bus:
                conv["from_bus"] = from_bus
                _add_bus(from_bus)

            out["converters"].append(conv)
        elif ctype == "storage":
            storage = dict(comp)
            # Champs UI internes/non metier: interdits par Vessel StorageCfg (extra="forbid").
            storage.pop("kind", None)
            storage.pop("vector_kind", None)
            storage_id = str(storage.get("id", "")).strip()
            raw_bus = storage.get("bus")
            if _is_nonempty(raw_bus) and not _is_auto_token(raw_bus):
                bus = _bus_id(str(raw_bus))
            else:
                bus = _bus_id(storage_id) if storage_id else ""
            if bus:
                storage["bus"] = bus
                _add_bus(bus)
            out["storages"].append(storage)

    return out


def _compile_with_checks(bundle: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    try:
        compiled = _compile_bundle_to_yaml(bundle)
        n_profiles = len(compiled.get("profiles", []) or [])
        n_converters = len(compiled.get("converters", []) or [])
        if n_profiles < 1 or n_converters < 1:
            return None, "Compilation echec: il faut au minimum 1 profil et 1 convertisseur."
        return compiled, "Compilation OK."
    except Exception as exc:  # noqa: BLE001
        return None, f"Compilation echec: {exc}"


def _default_result_columns(
    columns: list[str],
    profile_ids: list[str] | None = None,
    units_by_col: dict[str, str] | None = None,
) -> list[str]:
    cols = [str(c) for c in (columns or [])]
    if not cols:
        return []
    _ = profile_ids  # conserve la signature actuelle, non utilise.
    units_by_col = {str(k): str(v) for k, v in (units_by_col or {}).items()}

    out: list[str] = []
    out_set: set[str] = set()

    def _add(col: str) -> None:
        if col in cols and col not in out_set:
            out.append(col)
            out_set.add(col)

    # 1) time_s (exact attendu)
    _add("time_s")

    # 2) profils de vitesse uniquement (unitÃ© m/s)
    for c in cols:
        if c.startswith("profile_") and units_by_col.get(c, "") == "m/s":
            _add(c)

    # 3) stockages:
    # - priorite a *_v_stock_l et *_m_stock_kg
    # - sinon fallback *_e_stock_kWh (ou typo historique *_e_stoc_kWh)
    storage_prefixes: set[str] = set()
    for c in cols:
        if not c.startswith("storage_"):
            continue
        for suf in ("_v_stock_l", "_m_stock_kg", "_e_stock_kWh", "_e_stoc_kWh"):
            if c.endswith(suf):
                storage_prefixes.add(c[: -len(suf)])
                break

    for pref in sorted(storage_prefixes):
        v_col = f"{pref}_v_stock_l"
        m_col = f"{pref}_m_stock_kg"
        e_col = f"{pref}_e_stock_kWh"
        e_col_typo = f"{pref}_e_stoc_kWh"
        # Un seul trace par storage: priorite litre, sinon kWh.
        if v_col in cols:
            _add(v_col)
            continue
        if e_col in cols:
            _add(e_col)
            continue
        if e_col_typo in cols:
            _add(e_col_typo)
            continue
        # fallback dernier recours si pas de volume ni kWh
        if m_col in cols:
            _add(m_col)

    # Fallback minimal si rien de selectionne
    if not out:
        for c in cols[: min(6, len(cols))]:
            _add(c)

    return out


def _build_result_figure(
    rows: list[dict[str, Any]],
    selected_cols: list[str],
    units_by_col: dict[str, str] | None = None,
) -> go.Figure:
    fig = go.Figure()
    if not rows or not selected_cols:
        fig.update_layout(
            template="plotly_white",
            title="Aucune colonne selectionnee",
            height=320,
            margin={"l": 40, "r": 20, "t": 45, "b": 40},
        )
        return fig

    df = pd.DataFrame(rows)
    cols = [c for c in selected_cols if c in df.columns]
    if not cols:
        fig.update_layout(
            template="plotly_white",
            title="Selection invalide (colonnes absentes)",
            height=320,
            margin={"l": 40, "r": 20, "t": 45, "b": 40},
        )
        return fig

    time_col = None
    for cand in ["time", "t", "time_s", "time [s]", "time[s]"]:
        if cand in cols:
            time_col = cand
            break
    if time_col is None:
        for c in cols:
            lc = c.lower()
            if "time" in lc or lc.endswith("_s"):
                time_col = c
                break

    if time_col and time_col in df.columns:
        x = df[time_col]
        y_cols = [c for c in cols if c != time_col]
        x_title = time_col
    else:
        x = list(range(len(df)))
        y_cols = cols
        x_title = "Index"

    units_by_col = {str(k): str(v) for k, v in (units_by_col or {}).items()}

    # Groupe par unite pour creer 1 axe Y par grandeur/unite.
    grouped: dict[str, list[str]] = {}
    for c in y_cols:
        unit = units_by_col.get(c, "unitless")
        unit = unit if unit and unit.strip() else "unitless"
        grouped.setdefault(unit, []).append(c)

    axis_key_by_unit: dict[str, str] = {}
    for idx, unit in enumerate(grouped.keys(), start=1):
        axis_key_by_unit[unit] = "y" if idx == 1 else f"y{idx}"

    def _display_unit_label(unit: str) -> str:
        if unit == "l":
            return "litre"
        if unit == "l/s":
            return "litre/s"
        if unit == "m3/s":
            return "m³/s"
        if unit == "m3":
            return "m³"
        return unit

    n_axes = len(grouped)
    for axis_idx, unit in enumerate(grouped.keys(), start=1):
        axis_name = "yaxis" if axis_idx == 1 else f"yaxis{axis_idx}"
        title = _display_unit_label(unit)
        if axis_idx == 1:
            fig.update_layout(**{axis_name: {"title": title, "side": "left"}})
        else:
            pos = max(0.05, 1.0 - 0.07 * (axis_idx - 2))
            fig.update_layout(
                **{
                    axis_name: {
                        "title": title,
                        "overlaying": "y",
                        "side": "right",
                        "anchor": "free",
                        "position": pos,
                        "showgrid": False,
                    }
                }
            )

    for c in y_cols:
        unit = units_by_col.get(c, "unitless")
        axis_key = axis_key_by_unit.get(unit or "unitless", "y")
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df[c],
                mode="lines",
                name=c,
                yaxis=axis_key,
            )
        )

        fig.update_layout(
            template="plotly_white",
            title="Résultats simulation - Preview",
            height=320,
        margin={"l": 55, "r": max(30, 40 + 45 * max(0, n_axes - 1)), "t": 45, "b": 95},
        legend={"orientation": "h", "x": 0.0, "xanchor": "left", "y": -0.22},
    )
    fig.update_xaxes(title_text=x_title)
    return fig


def register_callbacks(app):
    def _next_rev(rev: int | None) -> int:
        return int(rev or 0) + 1
    
    si_hint = " Normalisation SI appliquée (Quantity): NavParams, PCI, niveaux initiaux."

    @app.callback(
        Output("v2db-rev", "data"),
        Input("v2db-refresh", "n_clicks"),
        Input("v2s-refresh", "n_clicks"),
        State("v2db-rev", "data"),
        prevent_initial_call=True,
    )
    def manual_refresh(_: int, __: int, rev: int | None):
        return _next_rev(rev)

    @app.callback(
        Output("v2s-current", "data", allow_duplicate=True),
        Output("v2s-select", "value", allow_duplicate=True),
        Output("v2s-status", "children", allow_duplicate=True),
        Output("v2c-json-store", "data", allow_duplicate=True),
        Output("v2c-yaml-store", "data", allow_duplicate=True),
        Output("v2c-status", "children", allow_duplicate=True),
        Input("v2s-refresh", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_schema_state(_: int):
        return {"name": "", "components": []}, None, "Schema reinitialise.", {}, {}, ""

    @app.callback(
        Output("v2m-form-seed", "data", allow_duplicate=True),
        Output("v2m-select", "value", allow_duplicate=True),
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-reset-guard", "data", allow_duplicate=True),
        Input("v2db-refresh", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_component_state(_: int):
        return {}, None, "Nouveau composant: formulaire reinitialise.", False

    @app.callback(
        Output("v2s-form-container", "children"),
        Input("v2s-current", "data"),
    )
    def render_schema_form_cb(current_schema: dict[str, Any] | None):
        safe = current_schema if isinstance(current_schema, dict) else {"name": "", "components": []}
        # Keep key stable while editing only the schema name to avoid visual refresh of table/form.
        key = json.dumps({"components": _schema_components_list(safe)}, ensure_ascii=False, sort_keys=True, default=str)
        return html.Div(render_schema_form(safe), key=key)

    @app.callback(
        Output("v2s-current", "data"),
        Output("v2s-status", "children"),
        Input(ModelForm.ids.main(SCHEMA_AIO_ID, SCHEMA_FORM_ID), "data"),
        State("v2s-current", "data"),
        prevent_initial_call=True,
    )
    def schema_form_to_store(form_data: dict[str, Any] | None, current_schema: dict[str, Any] | None):
        if not isinstance(form_data, dict):
            return no_update, no_update
        current = current_schema if isinstance(current_schema, dict) else {"name": "", "components": []}
        name = str(form_data.get("name", current.get("name", ""))).strip()
        comps = _schema_components_list(form_data)
        store = _schema_store(name, comps, _catalog())
        if store == current:
            return no_update, no_update
        return store, no_update

    @app.callback(
        Output("v2s-select", "options"),
        Output("v2cfg-mermaid", "chart"),
        Input("v2m-refresh", "n_intervals"),
        Input("v2db-rev", "data"),
        Input("v2s-current", "data"),
        Input("v2cfg-view-mode", "value"),
        Input("v2c-yaml-store", "data"),
    )
    def schema_refresh(
        _: int,
        __: int,
        current_schema: dict[str, Any] | None,
        view_mode: str | None,
        compiled_yaml: dict[str, Any] | None,
    ):
        schema_opts = [{"label": str(r.get("name", "")), "value": str(r.get("name", ""))} for r in list_schemas() if str(r.get("name", "")).strip()]
        current = current_schema if isinstance(current_schema, dict) else {"name": "schema_local", "components": []}
        mode = (view_mode or "simple").strip().lower()

        if mode == "yaml":
            if isinstance(compiled_yaml, dict) and compiled_yaml:
                try:
                    mermaid = yaml_to_mermaid(
                        compiled_yaml,
                        show_inputs=False,
                        show_input_labels=False,
                        show_bus_labels=False,
                        flow_direction="LR",
                    )
                except Exception:
                    mermaid = (
                        "flowchart LR\n"
                        "  n0[/Erreur rendu YAML/]\n"
                        "  classDef error fill:#ffebee,stroke:#c62828,stroke-width:2.4px,stroke-dasharray:8 5,color:#b71c1c,font-size:22px,font-weight:bold;\n"
                        "  class n0 error;"
                    )
            else:
                mermaid = (
                    "flowchart LR\n"
                    "  n0[/YAML pas compilé/]\n"
                    "  classDef error fill:#ffebee,stroke:#c62828,stroke-width:2.4px,stroke-dasharray:8 5,color:#b71c1c,font-size:22px,font-weight:bold;\n"
                    "  class n0 error;"
                )
        else:
            comps = _schema_components_list(current)
            mermaid = _schema_to_mermaid(comps, _catalog())
        return schema_opts, mermaid

    @app.callback(
        Output("v2s-current", "data", allow_duplicate=True),
        Output("v2s-status", "children", allow_duplicate=True),
        Input("v2s-load", "n_clicks"),
        State("v2s-select", "value"),
        prevent_initial_call=True,
    )
    def schema_load(_: int, selected: str | None):
        if not selected:
            return no_update, "Selectionne un schema."
        row = next((r for r in list_schemas() if str(r.get("name", "")) == str(selected)), None)
        schema = row.get("schema", {}) if isinstance(row, dict) else {}
        comps = _schema_components_list(schema if isinstance(schema, dict) else {})
        return _schema_store(str(selected), comps, _catalog()), f"Schema charge: {selected}"

    @app.callback(
        Output("v2s-current", "data", allow_duplicate=True),
        Output("v2s-status", "children", allow_duplicate=True),
        Output("v2s-pending-save", "data"),
        Output("v2s-update-modal", "opened"),
        Output("v2db-rev", "data", allow_duplicate=True),
        Input("v2s-save", "n_clicks"),
        State("v2s-current", "data"),
        State("v2db-rev", "data"),
        prevent_initial_call=True,
    )
    def schema_save(_: int, current_schema: dict[str, Any] | None, rev: int | None):
        current = current_schema if isinstance(current_schema, dict) else {"name": "", "components": []}
        schema_name = str(current.get("name", "")).strip()
        if not schema_name:
            return no_update, "Sauvegarde refusee: nom du schema requis.", {}, False, no_update
        ok, msg = _check_schema_save_constraints(current)
        if not ok:
            return no_update, msg, {}, False, no_update
        payload = _schema_db_payload(current)
        name = str(payload.get("name", ""))
        exists = any(str(r.get("name", "")) == name for r in list_schemas())
        if exists:
            return no_update, f"Le nom '{name}' existe deja. Confirmation requise.", payload, True, no_update
        upsert_schema(name, payload)
        refreshed = _schema_store(name, _schema_components_list(payload), _catalog())
        return refreshed, f"Schema sauvegarde en DB: {name}", {}, False, _next_rev(rev)

    @app.callback(
        Output("v2s-current", "data", allow_duplicate=True),
        Output("v2s-status", "children", allow_duplicate=True),
        Output("v2s-pending-save", "data", allow_duplicate=True),
        Output("v2s-update-modal", "opened", allow_duplicate=True),
        Output("v2db-rev", "data", allow_duplicate=True),
        Input("v2s-update-yes", "n_clicks"),
        State("v2s-pending-save", "data"),
        State("v2db-rev", "data"),
        prevent_initial_call=True,
    )
    def schema_confirm_update(_: int, pending: dict[str, Any] | None, rev: int | None):
        if not isinstance(pending, dict) or not pending:
            return no_update, "Aucune mise a jour en attente.", {}, False, no_update
        if not str(pending.get("name", "")).strip():
            return no_update, "Sauvegarde refusee: nom du schema requis.", {}, False, no_update
        ok, msg = _check_schema_save_constraints(pending)
        if not ok:
            return no_update, msg, {}, False, no_update
        name = str(pending.get("name", ""))
        upsert_schema(name, pending)
        refreshed = _schema_store(name, _schema_components_list(pending), _catalog())
        return refreshed, f"Schema mis a jour en DB: {name}", {}, False, _next_rev(rev)

    @app.callback(
        Output("v2s-update-modal", "opened", allow_duplicate=True),
        Input("v2s-update-no", "n_clicks"),
        prevent_initial_call=True,
    )
    def schema_cancel_update(_: int):
        return False

    @app.callback(
        Output("v2s-delete-modal", "opened"),
        Output("v2s-status", "children", allow_duplicate=True),
        Input("v2s-delete", "n_clicks"),
        State("v2s-select", "value"),
        prevent_initial_call=True,
    )
    def schema_request_delete(_: int, selected: str | None):
        if not selected:
            return False, "Selectionne un schema a supprimer."
        return True, "Confirmation suppression ouverte."

    @app.callback(
        Output("v2s-status", "children", allow_duplicate=True),
        Output("v2s-delete-modal", "opened", allow_duplicate=True),
        Output("v2db-rev", "data", allow_duplicate=True),
        Input("v2s-delete-yes", "n_clicks"),
        State("v2s-select", "value"),
        State("v2db-rev", "data"),
        prevent_initial_call=True,
    )
    def schema_confirm_delete(_: int, selected: str | None, rev: int | None):
        if not selected:
            return "Selectionne un schema a supprimer.", False, no_update
        row = next((r for r in list_schemas() if str(r.get("name", "")) == str(selected)), None)
        if not isinstance(row, dict):
            return "Schema introuvable.", False, no_update
        delete_schema(int(row["id"]))
        return f"Schema supprime: {selected}", False, _next_rev(rev)

    @app.callback(
        Output("v2s-delete-modal", "opened", allow_duplicate=True),
        Input("v2s-delete-no", "n_clicks"),
        prevent_initial_call=True,
    )
    def schema_cancel_delete(_: int):
        return False

    @app.callback(
        Output("v2s-status", "children", allow_duplicate=True),
        Output("v2c-json-store", "data"),
        Input("v2s-validate", "n_clicks"),
        State("v2s-current", "data"),
        prevent_initial_call=True,
    )
    def schema_validate(_: int, current_schema: dict[str, Any] | None):
        current = current_schema if isinstance(current_schema, dict) else {"name": "", "components": []}
        ok, msg = _check_schema_constraints_for_validate(current)
        if not ok:
            return msg, no_update
        name = str(current.get("name", "")).strip()
        if not name:
            return "Validation echec: nom du schema requis.", no_update
        if any(str(r.get("name", "")) == name for r in list_schemas()):
            return f"Attention: le nom '{name}' existe deja.", _build_schema_bundle(current)
        return "Validation OK: schema coherent.", _build_schema_bundle(current)

    @app.callback(
        Output("v2c-status", "children", allow_duplicate=True),
        Output("v2c-yaml-store", "data"),
        Input("v2c-compile", "n_clicks"),
        State("v2c-json-store", "data"),
        State("v2s-current", "data"),
        prevent_initial_call=True,
    )
    def compile_bundle(_: int, bundle: dict[str, Any] | None, current_schema: dict[str, Any] | None):
        work_bundle = bundle if isinstance(bundle, dict) and bundle else None
        if work_bundle is None:
            work_bundle, msg = _build_bundle_from_current_schema(current_schema)
            if work_bundle is None:
                return msg, no_update

        compiled, msg = _compile_with_checks(work_bundle)
        if compiled is None:
            return msg, no_update
        return msg, compiled

    @app.callback(
        Output("v2c-status", "children", allow_duplicate=True),
        Output("v2r-sim-summary", "children"),
        Output("v2sim-last-run", "data"),
        Output("v2sim-df-store", "data"),
        Output("v2c-yaml-store", "data", allow_duplicate=True),
        Input("v2c-simulate", "n_clicks"),
        State("v2c-json-store", "data"),
        State("v2s-current", "data"),
        State("v2c-yaml-store", "data"),
        prevent_initial_call=True,
    )
    def simulate_from_compiled(
        _: int,
        bundle: dict[str, Any] | None,
        current_schema: dict[str, Any] | None,
        compiled_from_store: dict[str, Any] | None,
    ):
        work_bundle = bundle if isinstance(bundle, dict) and bundle else None
        if work_bundle is None:
            work_bundle, msg = _build_bundle_from_current_schema(current_schema)
            if work_bundle is None:
                return msg, no_update, no_update, no_update, no_update

        compiled, msg = _compile_with_checks(work_bundle)
        if compiled is None:
            return msg, no_update, no_update, no_update, no_update

        try:
            yaml_text = yaml.safe_dump(compiled, allow_unicode=True, sort_keys=False)
            out = run_simulation_from_yaml(yaml_text)
            df_export = out.dataframe.where(pd.notna(out.dataframe), None)
            rows = df_export.to_dict(orient="records")
            profile_ids = [str(p.get("id", "")).strip() for p in (compiled.get("profiles", []) or []) if isinstance(p, dict)]
            default_cols = _default_result_columns(
                out.columns,
                profile_ids=profile_ids,
                units_by_col=out.units,
            )
            summary = html.Div(
                [
                    html.H4("Derniere simulation", style={"marginTop": "0", "marginBottom": "6px"}),
                    html.Div(f"Lignes: {out.n_rows}"),
                    html.Div(f"Colonnes: {len(out.columns)}"),
                ]
            )
            meta = {
                "n_rows": out.n_rows,
                "n_cols": len(out.columns),
                "columns": out.columns,
                "units": out.units,
            }
            df_store = {
                "columns": out.columns,
                "rows": rows,
                "default_columns": default_cols,
                "selected_columns": default_cols,
                "units": out.units,
            }
            return "Simulation OK.", summary, meta, df_store, compiled
        except Exception as exc:  # noqa: BLE001
            # En cas d'echec simulation, on garde le YAML compilé issu de ce clic.
            fallback_yaml = compiled if isinstance(compiled, dict) else compiled_from_store
            return f"Simulation echec: {exc}", no_update, no_update, no_update, fallback_yaml

    @app.callback(
        Output("v2r-cols", "options"),
        Output("v2r-cols", "value"),
        Input("v2sim-df-store", "data"),
    )
    def init_results_columns(df_store: dict[str, Any] | None):
        if not isinstance(df_store, dict) or not df_store:
            return [], []

        columns = [str(c) for c in (df_store.get("columns", []) or [])]
        options = [{"label": c, "value": c} for c in columns]
        selected = [str(c) for c in (df_store.get("default_columns", []) or []) if str(c) in set(columns)]
        if not selected:
            selected = columns[: min(6, len(columns))]
        return options, selected

    @app.callback(
        Output("v2r-graph", "figure"),
        Input("v2sim-df-store", "data"),
        Input("v2r-cols", "value"),
    )
    def refresh_results_graph(df_store: dict[str, Any] | None, selected: list[str] | None):
        if not isinstance(df_store, dict) or not df_store:
            fig = _build_result_figure([], [])
            return fig

        columns = [str(c) for c in (df_store.get("columns", []) or [])]
        rows = df_store.get("rows", []) or []
        units_by_col = {
            str(k): str(v)
            for k, v in (df_store.get("units", {}) or {}).items()
        }

        selected_clean = [str(c) for c in (selected or []) if str(c) in set(columns)]
        if not selected_clean:
            selected_clean = [str(c) for c in (df_store.get("default_columns", []) or []) if str(c) in set(columns)]
        if not selected_clean:
            selected_clean = columns[: min(6, len(columns))]

        fig = _build_result_figure(rows, selected_clean, units_by_col=units_by_col)
        return fig

    @app.callback(
        Output("v2r-csv-download", "data"),
        Output("v2c-status", "children", allow_duplicate=True),
        Input("v2r-export-csv", "n_clicks"),
        State("v2sim-df-store", "data"),
        State("v2r-cols", "value"),
        prevent_initial_call=True,
    )
    def export_results_csv(_: int, df_store: dict[str, Any] | None, selected: list[str] | None):
        if not isinstance(df_store, dict) or not df_store:
            return no_update, "Export CSV refuse: aucun resultat de simulation."
        rows = df_store.get("rows", []) or []
        if not rows:
            return no_update, "Export CSV refuse: tableau resultat vide."
        df = pd.DataFrame(rows)
        selected_cols = [str(c) for c in (selected or []) if str(c) in df.columns]
        if not selected_cols:
            selected_cols = [str(c) for c in (df_store.get("default_columns", []) or []) if str(c) in df.columns]
        if not selected_cols:
            return no_update, "Export CSV refuse: aucune colonne valide selectionnee."
        export_df = df[selected_cols].copy()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"simulation_results_{stamp}.csv"
        return dcc.send_data_frame(export_df.to_csv, filename, index=False), f"Export CSV OK: {filename}"

    @app.callback(
        Output("v2c-json-modal", "opened"),
        Output("v2c-json-content", "children"),
        Input("v2c-show-json", "n_clicks"),
        State("v2c-json-store", "data"),
        prevent_initial_call=True,
    )
    def show_json(_: int, bundle: dict[str, Any] | None):
        text = json.dumps(bundle or {}, ensure_ascii=False, indent=2, sort_keys=True)
        return True, text

    @app.callback(
        Output("v2c-yaml-modal", "opened"),
        Output("v2c-yaml-content", "children"),
        Input("v2c-show-yaml", "n_clicks"),
        State("v2c-yaml-store", "data"),
        prevent_initial_call=True,
    )
    def show_yaml(_: int, compiled: dict[str, Any] | None):
        text = yaml.safe_dump(compiled or {}, allow_unicode=True, sort_keys=False)
        return True, text

    @app.callback(
        Output("v2c-json-modal", "opened", allow_duplicate=True),
        Input("v2c-json-close", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_json_modal(_: int):
        return False

    @app.callback(
        Output("v2c-yaml-modal", "opened", allow_duplicate=True),
        Input("v2c-yaml-close", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_yaml_modal(_: int):
        return False

    @app.callback(
        Output("v2r-plot-modal", "opened"),
        Output("v2r-graph-large", "figure"),
        Input("v2r-open-plot", "n_clicks"),
        State("v2r-graph", "figure"),
        prevent_initial_call=True,
    )
    def open_large_plot(_: int, fig: dict[str, Any] | None):
        out_fig = fig if isinstance(fig, dict) else {"data": [], "layout": {"template": "plotly_white"}}
        layout = out_fig.setdefault("layout", {})
        if isinstance(layout, dict):
            layout["height"] = 720
            layout["title"] = "Résultats simulation - Preview"
        return True, out_fig

    @app.callback(
        Output("v2r-plot-modal", "opened", allow_duplicate=True),
        Input("v2r-close-plot", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_large_plot(_: int):
        return False

    @app.callback(
        Output("v2m-select", "options"),
        Input("v2m-refresh", "n_intervals"),
        Input("v2db-rev", "data"),
    )
    def selector_options(_: int, __: int):
        return [{"label": str(r.get("name", "")), "value": str(r.get("name", ""))} for r in db_rows() if str(r.get("name", "")).strip()]

    @app.callback(
        Output("v2m-model", "options"),
        Output("v2m-model", "value"),
        Input("v2m-type", "value"),
        State("v2m-model", "value"),
    )
    def update_model_options(component_type: str, current_model: str | None):
        ctype = component_type or "converter"
        options = model_options(ctype)
        allowed = {str(opt.get("value", "")) for opt in options}
        if current_model and str(current_model) in allowed:
            return options, current_model
        return options, default_model_key(ctype)

    @app.callback(
        Output("v2m-form-container", "children"),
        Input("v2m-model", "value"),
        Input("v2m-form-seed", "data"),
    )
    def render_form_cb(model_key: str | None, seed: dict[str, Any] | None):
        safe_seed = seed if isinstance(seed, dict) else {}
        seed_json = json.dumps(safe_seed, ensure_ascii=False, sort_keys=True, default=str)
        form_key = f"{model_key or 'none'}::{seed_json}"
        return html.Div(render_form(model_key, safe_seed), key=form_key)

    @app.callback(
        Output("v2m-form-seed", "data", allow_duplicate=True),
        Input(ModelForm.ids.main(AIO_ID, FORM_ID), "data"),
        State("v2m-model", "value"),
        State("v2m-form-seed", "data"),
        prevent_initial_call=True,
    )
    def nav_course_filter_seed(
        form_data: dict[str, Any] | None,
        model_key: str | None,
        current_seed: dict[str, Any] | None,
    ):
        if model_key != "profile.nav_speed":
            return no_update
        if not isinstance(form_data, dict):
            return no_update

        prev = current_seed if isinstance(current_seed, dict) else {}
        prev_id = str(prev.get("id", "")).strip()
        form_id = str(form_data.get("id", "")).strip()
        if prev_id and form_id and prev_id != form_id:
            return no_update

        prev_select = str(prev.get("select", "cruise"))
        form_select = str(form_data.get("select", "cruise"))
        prev_course_no = prev.get("course_no")
        form_course_no = form_data.get("course_no")
        if (
            prev_select == "course"
            and form_select == "cruise"
            and prev_course_no not in (None, "")
            and form_course_no in (None, "")
        ):
            return no_update

        cruise_name = str(form_data.get("cruise_name", ""))
        select_mode = str(form_data.get("select", "cruise"))
        if cruise_name == str(prev.get("cruise_name", "")) and select_mode == str(prev.get("select", "cruise")):
            return no_update

        seed = dict(form_data)
        if select_mode != "course":
            seed["course_no"] = None
            return seed

        allowed = {str(n) for n in COURSES_NUMBER.get(cruise_name, [])}
        course_no = seed.get("course_no")
        if course_no is not None and str(course_no) not in allowed:
            seed["course_no"] = None
        return seed

    @app.callback(
        Output("v2m-type", "value", allow_duplicate=True),
        Output("v2m-model", "value", allow_duplicate=True),
        Output("v2m-form-seed", "data", allow_duplicate=True),
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-reset-guard", "data", allow_duplicate=True),
        Input("v2m-load-edit", "n_clicks"),
        State("v2m-select", "value"),
        prevent_initial_call=True,
    )
    def load_edit(_: int, selected_name: str | None):
        if not selected_name:
            return no_update, no_update, no_update, "Selectionne un composant a editer.", no_update
        t = get_template_by_name(selected_name)
        if t is None:
            return no_update, no_update, no_update, "Composant DB introuvable.", no_update
        ctype = str(t.get("component_type", ""))
        kind = str(t.get("kind", ""))
        model_key, seed = seed_from_template(ctype, kind, t.get("payload", {}))
        if model_key is None:
            return no_update, no_update, no_update, "Type/Kind non supporte par ce formulaire.", no_update
        return ctype, model_key, seed, f"Edition chargee: {selected_name}", True

    @app.callback(
        Output("v2m-form-seed", "data", allow_duplicate=True),
        Output("v2m-select", "value", allow_duplicate=True),
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-reset-guard", "data", allow_duplicate=True),
        Input("v2m-type", "value"),
        Input("v2m-model", "value"),
        State("v2m-reset-guard", "data"),
        prevent_initial_call=True,
    )
    def reset_form_on_type_model_change(
        _: str | None,
        __: str | None,
        reset_guard: bool | None,
    ):
        if bool(reset_guard):
            return no_update, no_update, no_update, False
        return {}, None, "Nouveau composant: formulaire reinitialise.", False

    @app.callback(
        Output("v2m-status", "children"),
        Input("v2m-validate", "n_clicks"),
        State("v2m-model", "value"),
        State(ModelForm.ids.main(AIO_ID, FORM_ID), "data"),
        prevent_initial_call=True,
    )
    def validate(_: int, model_key: str | None, form_data: dict[str, Any] | None):
        if not model_key:
            return "Choisis un modele."
        if not isinstance(form_data, dict):
            return "Formulaire vide."
        try:
            raw = validate_form_data(model_key, form_data)
            name = str(raw.get("id", "")).strip()
            if not name:
                return "Erreur validation: nom requis."
            if get_template_by_name(name) is not None:
                return f"Attention: le nom '{name}' existe deja."
            return f"Validation OK.{si_hint}"
        except ValidationError as exc:
            return f"Erreur validation: {exc.errors()}"
        except Exception as exc:  # noqa: BLE001
            return f"Erreur: {exc}"

    @app.callback(
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-pending-save", "data"),
        Output("v2m-update-modal", "opened"),
        Output("v2db-rev", "data", allow_duplicate=True),
        Input("v2m-save", "n_clicks"),
        State("v2m-model", "value"),
        State(ModelForm.ids.main(AIO_ID, FORM_ID), "data"),
        State("v2db-rev", "data"),
        prevent_initial_call=True,
    )
    def save_component(_: int, model_key: str | None, form_data: dict[str, Any] | None, rev: int | None):
        if not model_key:
            return "Choisis un modele.", no_update, False, no_update
        if not isinstance(form_data, dict):
            return "Formulaire vide.", no_update, False, no_update
        try:
            raw = validate_form_data(model_key, form_data)
            name = str(raw.get("id", "")).strip()
            if not name:
                return "Nom requis.", no_update, False, no_update
            ctype, kind, payload = payload_from_data(model_key, raw)
            exists = get_template_by_name(name) is not None
            pending = {"name": name, "component_type": ctype, "kind": kind, "payload": payload}
            if exists:
                return f"Le nom '{name}' existe deja. Confirmation requise.{si_hint}", pending, True, no_update
            upsert_template(name=name, family="General", component_type=ctype, kind=kind, payload=payload)
            return f"Composant sauvegarde en DB: {name}.{si_hint}", {}, False, _next_rev(rev)
        except ValidationError as exc:
            return f"Erreur validation: {exc.errors()}", no_update, False, no_update
        except Exception as exc:  # noqa: BLE001
            return f"Erreur sauvegarde: {exc}", no_update, False, no_update

    @app.callback(
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-pending-save", "data", allow_duplicate=True),
        Output("v2m-update-modal", "opened", allow_duplicate=True),
        Output("v2db-rev", "data", allow_duplicate=True),
        Input("v2m-update-yes", "n_clicks"),
        State("v2m-pending-save", "data"),
        State("v2db-rev", "data"),
        prevent_initial_call=True,
    )
    def confirm_update(_: int, pending: dict[str, Any] | None, rev: int | None):
        if not isinstance(pending, dict) or not pending:
            return "Aucune mise a jour en attente.", {}, False, no_update
        upsert_template(
            name=str(pending.get("name", "")),
            family="General",
            component_type=str(pending.get("component_type", "")),
            kind=str(pending.get("kind", "")),
            payload=pending.get("payload", {}),
        )
        return f"Composant DB mis a jour: {str(pending.get('name', ''))}.{si_hint}", {}, False, _next_rev(rev)

    @app.callback(
        Output("v2m-update-modal", "opened", allow_duplicate=True),
        Input("v2m-update-no", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_update(_: int):
        return False

    @app.callback(
        Output("v2m-delete-modal", "opened"),
        Output("v2m-status", "children", allow_duplicate=True),
        Input("v2m-delete", "n_clicks"),
        State("v2m-select", "value"),
        prevent_initial_call=True,
    )
    def request_delete(_: int, selected_value: str | None):
        if not selected_value:
            return False, "Selectionne un composant a supprimer."
        return True, "Confirmation suppression ouverte."

    @app.callback(
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-delete-modal", "opened", allow_duplicate=True),
        Output("v2db-rev", "data", allow_duplicate=True),
        Input("v2m-delete-yes", "n_clicks"),
        State("v2m-select", "value"),
        State("v2db-rev", "data"),
        prevent_initial_call=True,
    )
    def confirm_delete(_: int, selected_value: str | None, rev: int | None):
        if not selected_value:
            return "Aucune selection a supprimer.", False, no_update
        t = get_template_by_name(selected_value)
        if t is None:
            return "Composant DB introuvable.", False, no_update
        delete_template(int(t["id"]))
        return f"Composant DB supprime: {selected_value}", False, _next_rev(rev)

    @app.callback(
        Output("v2m-delete-modal", "opened", allow_duplicate=True),
        Input("v2m-delete-no", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_delete(_: int):
        return False
