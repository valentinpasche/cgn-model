"""Callbacks UI V2 composants (DB-only)."""

from __future__ import annotations

import json
import re
from typing import Any

from dash import Input, Output, State, ctx, html, no_update
from dash_pydantic_form import ModelForm
from pydantic import ValidationError

from components_basemodel import COURSES_NUMBER
from components_registry import (
    AIO_ID,
    FORM_ID,
    db_rows,
    default_model_key,
    model_options,
    payload_from_data,
    render_form,
    seed_from_template,
    validate_form_data,
)
from services.storage import (
    delete_schema,
    delete_template,
    get_template_by_name,
    list_schemas,
    upsert_schema,
    upsert_template,
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
    # remove duplicates preserving order
    uniq: list[str] = []
    seen: set[str] = set()
    for n in out:
        if n not in seen:
            uniq.append(n)
            seen.add(n)
    return uniq


def _schema_payload(name: str, components: list[str]) -> dict[str, Any]:
    return {"name": name, "components": components}


def _catalog() -> dict[str, dict[str, Any]]:
    return {str(r.get("name", "")): r for r in db_rows() if str(r.get("name", "")).strip()}


def _schema_table_rows(schema_components: list[str], catalog: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for comp_id in schema_components:
        item = catalog.get(comp_id)
        if item is None:
            rows.append({"id": comp_id, "status": "INCONNU", "model": "NA"})
            continue
        model = f"{item.get('component_type', '')}.{item.get('kind', '')}"
        t = get_template_by_name(comp_id)
        if isinstance(t, dict):
            mk, _ = seed_from_template(str(t.get("component_type", "")), str(t.get("kind", "")), t.get("payload", {}))
            if mk:
                model = mk
        rows.append({"id": comp_id, "status": "OK", "model": model})
    return rows


def _schema_edges(schema_components: list[str]) -> list[tuple[str, str]]:
    names = set(schema_components)
    edges: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for dst in schema_components:
        t = get_template_by_name(dst)
        if not isinstance(t, dict):
            continue
        ctype = str(t.get("component_type", ""))
        kind = str(t.get("kind", ""))
        _, seed = seed_from_template(ctype, kind, t.get("payload", {}))
        d = seed if isinstance(seed, dict) else {}

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

        for src in refs:
            if src in names and src != dst:
                edge = (src, dst)
                if edge not in seen:
                    seen.add(edge)
                    edges.append(edge)
    return edges


def _schema_to_mermaid(schema_components: list[str], catalog: dict[str, dict[str, Any]]) -> str:
    if not schema_components:
        return 'flowchart LR\n  n0["Schema vide"]'

    def sanitize(raw: str) -> str:
        cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", raw)
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned or "node"

    node_ids: dict[str, str] = {}
    lines: list[str] = ["flowchart LR"]
    for idx, comp_id in enumerate(schema_components, start=1):
        node_ids[comp_id] = f"n_{sanitize(comp_id)}_{idx}"

    for comp_id in schema_components:
        node_id = node_ids[comp_id]
        item = catalog.get(comp_id)
        if item is None:
            lines.append(f'  {node_id}["ERROR: unknown_ref:{comp_id}"]')
            continue
        ctype = str(item.get("component_type", ""))
        if ctype == "profile":
            lines.append(f'  {node_id}[("{comp_id}")]')
        elif ctype == "adapter":
            lines.append(f'  {node_id}{{{{"{comp_id}"}}}}')
        elif ctype == "converter":
            lines.append(f'  {node_id}["{comp_id}"]')
        elif ctype == "storage":
            lines.append(f'  {node_id}((("{comp_id}")))')
        else:
            lines.append(f'  {node_id}["{comp_id}"]')

    for src, dst in _schema_edges(schema_components):
        lines.append(f"  {node_ids[src]} --> {node_ids[dst]}")

    unknown_nodes = [node_ids[c] for c in schema_components if c not in catalog]
    if unknown_nodes:
        lines.append("  classDef unknown fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#b71c1c;")
        lines.append(f"  class {','.join(unknown_nodes)} unknown;")
    return "\n".join(lines)


def _validate_schema(schema_components: list[str], catalog: dict[str, dict[str, Any]]) -> str:
    if not schema_components:
        return "Validation echec: schema vide."
    missing = [c for c in schema_components if c not in catalog]
    if missing:
        return f"Validation echec: composants manquants -> {', '.join(missing)}"

    incoming = {c: 0 for c in schema_components}
    outgoing = {c: 0 for c in schema_components}
    for src, dst in _schema_edges(schema_components):
        outgoing[src] += 1
        incoming[dst] += 1
    isolated = [c for c in schema_components if incoming[c] == 0 and outgoing[c] == 0]
    if isolated:
        return f"Validation echec: composants isoles -> {', '.join(isolated)}"
    return "Validation OK: schema coherent."


def register_callbacks(app):
    def _next_rev(rev: int | None) -> int:
        return int(rev or 0) + 1

    @app.callback(
        Output("v2db-rev", "data"),
        Input("v2db-refresh", "n_clicks"),
        State("v2db-rev", "data"),
        prevent_initial_call=True,
    )
    def manual_refresh(_: int, rev: int | None):
        return _next_rev(rev)

    @app.callback(
        Output("v2s-name", "value"),
        Input("v2s-current", "data"),
    )
    def schema_name_reflect(current_schema: dict[str, Any] | None):
        current = current_schema if isinstance(current_schema, dict) else {}
        return str(current.get("name", "schema_local"))

    @app.callback(
        Output("v2s-add-component", "options"),
        Output("v2s-remove-component", "options"),
        Output("v2s-select", "options"),
        Output("v2s-table", "data"),
        Output("v2cfg-mermaid", "chart"),
        Input("v2m-refresh", "n_intervals"),
        Input("v2db-rev", "data"),
        Input("v2s-current", "data"),
    )
    def schema_refresh(_: int, __: int, current_schema: dict[str, Any] | None):
        catalog = _catalog()
        current = current_schema if isinstance(current_schema, dict) else {"name": "schema_local", "components": []}
        comps = _schema_components_list(current)
        add_opts = [{"label": n, "value": n} for n in sorted(catalog.keys())]
        rem_opts = [{"label": n, "value": n} for n in comps]
        schema_opts = [{"label": str(r.get("name", "")), "value": str(r.get("name", ""))} for r in list_schemas() if str(r.get("name", "")).strip()]
        table_rows = _schema_table_rows(comps, catalog)
        mermaid = _schema_to_mermaid(comps, catalog)
        return add_opts, rem_opts, schema_opts, table_rows, mermaid

    @app.callback(
        Output("v2s-current", "data"),
        Output("v2s-status", "children"),
        Input("v2s-add-btn", "n_clicks"),
        State("v2s-add-component", "value"),
        State("v2s-current", "data"),
        prevent_initial_call=True,
    )
    def schema_add_component(_: int, comp_name: str | None, current_schema: dict[str, Any] | None):
        if not comp_name:
            return no_update, "Selectionne un composant a ajouter."
        current = current_schema if isinstance(current_schema, dict) else {"name": "schema_local", "components": []}
        name = str(current.get("name", "schema_local"))
        comps = _schema_components_list(current)
        if comp_name in comps:
            return no_update, f"Le composant '{comp_name}' est deja dans le schema."
        comps.append(str(comp_name))
        return _schema_payload(name, comps), f"Composant ajoute: {comp_name}"

    @app.callback(
        Output("v2s-current", "data", allow_duplicate=True),
        Output("v2s-status", "children", allow_duplicate=True),
        Input("v2s-remove-btn", "n_clicks"),
        State("v2s-remove-component", "value"),
        State("v2s-current", "data"),
        prevent_initial_call=True,
    )
    def schema_remove_component(_: int, comp_name: str | None, current_schema: dict[str, Any] | None):
        if not comp_name:
            return no_update, "Selectionne un composant a supprimer."
        current = current_schema if isinstance(current_schema, dict) else {"name": "schema_local", "components": []}
        name = str(current.get("name", "schema_local"))
        comps = [c for c in _schema_components_list(current) if c != str(comp_name)]
        return _schema_payload(name, comps), f"Composant supprime: {comp_name}"

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
        return _schema_payload(str(selected), comps), f"Schema charge: {selected}"

    @app.callback(
        Output("v2s-current", "data", allow_duplicate=True),
        Output("v2s-status", "children", allow_duplicate=True),
        Output("v2db-rev", "data", allow_duplicate=True),
        Input("v2s-save", "n_clicks"),
        State("v2s-current", "data"),
        State("v2s-name", "value"),
        State("v2db-rev", "data"),
        prevent_initial_call=True,
    )
    def schema_save(_: int, current_schema: dict[str, Any] | None, save_name: str | None, rev: int | None):
        current = current_schema if isinstance(current_schema, dict) else {"name": "schema_local", "components": []}
        name = str(save_name or current.get("name", "schema_local")).strip() or "schema_local"
        comps = _schema_components_list(current)
        payload = _schema_payload(name, comps)
        upsert_schema(name, payload)
        return payload, f"Schema sauvegarde en DB: {name}", _next_rev(rev)

    @app.callback(
        Output("v2s-status", "children", allow_duplicate=True),
        Output("v2db-rev", "data", allow_duplicate=True),
        Input("v2s-delete", "n_clicks"),
        State("v2s-select", "value"),
        State("v2db-rev", "data"),
        prevent_initial_call=True,
    )
    def schema_delete(_: int, selected: str | None, rev: int | None):
        if not selected:
            return "Selectionne un schema a supprimer.", no_update
        row = next((r for r in list_schemas() if str(r.get("name", "")) == str(selected)), None)
        if not isinstance(row, dict):
            return "Schema introuvable.", no_update
        delete_schema(int(row["id"]))
        return f"Schema supprime: {selected}", _next_rev(rev)

    @app.callback(
        Output("v2s-status", "children", allow_duplicate=True),
        Input("v2s-validate", "n_clicks"),
        State("v2s-current", "data"),
        prevent_initial_call=True,
    )
    def schema_validate(_: int, current_schema: dict[str, Any] | None):
        current = current_schema if isinstance(current_schema, dict) else {"name": "schema_local", "components": []}
        comps = _schema_components_list(current)
        return _validate_schema(comps, _catalog())

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
        Input("v2m-load-edit", "n_clicks"),
        State("v2m-select", "value"),
        prevent_initial_call=True,
    )
    def load_edit(_: int, selected_name: str | None):
        if not selected_name:
            return no_update, no_update, no_update, "Selectionne un composant a editer."
        t = get_template_by_name(selected_name)
        if t is None:
            return no_update, no_update, no_update, "Composant DB introuvable."
        ctype = str(t.get("component_type", ""))
        kind = str(t.get("kind", ""))
        model_key, seed = seed_from_template(ctype, kind, t.get("payload", {}))
        if model_key is None:
            return no_update, no_update, no_update, "Type/Kind non supporte par ce formulaire."
        return ctype, model_key, seed, f"Edition chargee: {selected_name}"

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
            return "Validation OK."
        except ValidationError as exc:
            return f"Erreur validation: {exc.errors()}"
        except Exception as exc:  # noqa: BLE001
            return f"Erreur: {exc}"

    @app.callback(
        Output("v2m-save-choice", "style"),
        Input("v2m-save", "n_clicks"),
        Input("v2m-save-cancel", "n_clicks"),
        Input("v2m-save-db", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_save_choice(_: int, __: int, ___: int):
        if ctx.triggered_id == "v2m-save":
            return {"display": "block", "marginTop": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"}
        return {"display": "none", "marginTop": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"}

    @app.callback(
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-pending-save", "data"),
        Output("v2m-update-modal", "opened"),
        Output("v2db-rev", "data", allow_duplicate=True),
        Input("v2m-save-db", "n_clicks"),
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
                return f"Le nom '{name}' existe deja. Confirmation requise.", pending, True, no_update
            upsert_template(name=name, family="General", component_type=ctype, kind=kind, payload=payload)
            return f"Composant sauvegarde en DB: {name}", {}, False, _next_rev(rev)
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
        return f"Composant DB mis a jour: {str(pending.get('name', ''))}", {}, False, _next_rev(rev)

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
