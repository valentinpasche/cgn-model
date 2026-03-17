"""
UI V2 orientee metier bateau (sans YAML expose par defaut).
"""

from __future__ import annotations

import json
from typing import Any, get_args, get_origin

from dash import ALL, Dash, Input, Output, State, callback, ctx, dash_table, dcc, html, no_update
from dash.exceptions import PreventUpdate
from dash_extensions import Mermaid
import plotly.graph_objects as go
from pydantic import ValidationError

from models.component_forms import forms_for_component_type, infer_form_key, model_for_key
from services.assembler import blank_schema, build_yaml_config_from_schema, to_yaml_text, yaml_to_simple_mermaid
from services.simulation import run_simulation_from_cfg
from services.storage import (
    delete_template,
    get_schema,
    get_template,
    init_db,
    list_schemas,
    list_templates,
    upsert_schema,
    upsert_template,
)


TYPE_OPTIONS = [
    {"label": "Profil (signal entree)", "value": "profile"},
    {"label": "Adaptateur (transformateur signal)", "value": "adapter"},
    {"label": "Convertisseur puissance (watt)", "value": "converter"},
    {"label": "Stockage energie", "value": "storage"},
]


def _default_payload_by_type(component_type: str) -> dict[str, Any]:
    if component_type == "profile":
        return {"component": {"id": "", "kind": "constant", "unit": "W", "value": 0.0}}
    if component_type == "adapter":
        return {
            "component": {
                "id": "",
                "kind": "speed_to_power_poly",
                "source": "",
                "unit_in": "m/s",
                "unit_out": "W",
                "params": {"coeffs": [0.0]},
            }
        }
    if component_type == "converter":
        return {
            "component": {
                "id": "",
                "kind": "constant_eta",
                "from_bus": "",
                "to_bus": "",
                "params": {"eta": 0.9},
            }
        }
    if component_type == "storage":
        return {"component": {"id": "", "bus": "", "vecteur": "diesel"}}
    return {"component": {"id": ""}}


def _form_options(component_type: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for key, model_cls in forms_for_component_type(component_type):
        out.append({"label": model_cls.ui_label(), "value": key})
    return out


def _default_form_key(component_type: str) -> str | None:
    opts = _form_options(component_type)
    if not opts:
        return None
    return str(opts[0]["value"])


def _build_form_children(form_key: str | None, initial: dict[str, Any] | None) -> list[Any]:
    if not form_key:
        return [html.Div("Aucun modele disponible pour ce type.")]
    model_cls = model_for_key(form_key)
    if model_cls is None:
        return [html.Div("Modele introuvable.")]
    initial_map = initial or {}
    children: list[Any] = []
    for field_name, field in model_cls.model_fields.items():
        default = initial_map.get(field_name, field.default if field.default is not None else "")
        ann = field.annotation
        origin = get_origin(ann)
        args = get_args(ann)
        if origin is not None and len(args) == 2 and type(None) in args:
            ann = args[0] if args[1] is type(None) else args[1]
        children.append(html.Label(field_name.replace("_", " ").capitalize()))
        if ann is bool:
            children.append(
                dcc.Dropdown(
                    id={"type": "v2-form-field", "field": field_name},
                    options=[{"label": "Oui", "value": "true"}, {"label": "Non", "value": "false"}],
                    value="true" if bool(default) else "false",
                    clearable=False,
                    style={"marginBottom": "6px"},
                )
            )
        elif ann in (float, int):
            children.append(
                dcc.Input(
                    id={"type": "v2-form-field", "field": field_name},
                    type="number",
                    value=default,
                    style={"width": "100%", "marginBottom": "6px"},
                )
            )
        else:
            children.append(
                dcc.Input(
                    id={"type": "v2-form-field", "field": field_name},
                    type="text",
                    value=str(default) if default is not None else "",
                    style={"width": "100%", "marginBottom": "6px"},
                )
            )
    return children


def _payload_from_form(form_key: str, ids: list[dict[str, str]], values: list[Any]) -> tuple[str, dict[str, Any]]:
    model_cls = model_for_key(form_key)
    if model_cls is None:
        raise ValueError("Modele formulaire introuvable.")
    kwargs: dict[str, Any] = {}
    for meta, value in zip(ids, values):
        field = str(meta.get("field", ""))
        if not field:
            continue
        if value is None or value == "":
            continue
        if isinstance(value, str) and value in ("true", "false"):
            kwargs[field] = value == "true"
        else:
            kwargs[field] = value
    form_obj = model_cls.model_validate(kwargs)
    component = form_obj.to_component()
    return model_cls.kind(), {"component": component}


def _template_options() -> list[dict[str, Any]]:
    rows = list_templates()
    return [{"label": f'{r["name"]} ({r["component_type"]})', "value": r["id"]} for r in rows]


def _template_table_rows() -> list[dict[str, Any]]:
    rows = list_templates()
    return [
        {
            "id": r["id"],
            "type": r["component_type"],
            "kind": r["kind"],
            "nom": r["name"],
            "modifie_le": r["updated_at"],
        }
        for r in rows
    ]


def _schema_options() -> list[dict[str, Any]]:
    rows = list_schemas()
    return [{"label": r["name"], "value": r["id"]} for r in rows]


def _instances_table(schema: dict[str, Any], templates_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for inst in schema.get("instances", []):
        tid = int(inst.get("template_id", 0))
        t = templates_by_id.get(tid, {})
        out.append(
            {
                "instance_id": str(inst.get("instance_id", "")),
                "type": str(t.get("component_type", "")),
                "kind": str(t.get("kind", "")),
                "source": str(inst.get("source", "") or ""),
                "bus": str(inst.get("bus", "") or ""),
                "from_bus": str(inst.get("from_bus", "") or ""),
                "to_bus": str(inst.get("to_bus", "") or ""),
            }
        )
    return out


def _profiles_plot(df) -> go.Figure:
    fig = go.Figure()
    time_col = "time_s" if "time_s" in df.columns else None
    profile_cols = [c for c in df.columns if c.endswith("_m_per_s") or c.endswith("_W")]
    if time_col:
        x = df[time_col]
        x_title = time_col
    else:
        x = df.index
        x_title = "index"
    for col in profile_cols[:8]:
        fig.add_trace(go.Scatter(x=x, y=df[col], mode="lines", name=col))
    if not fig.data:
        fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers", name="Aucune courbe"))
    fig.update_layout(title="Simulation energetique", showlegend=True, xaxis_title=x_title)
    return fig


init_db()
app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "CGN UI V2 - Bateau"

app.layout = html.Div(
    [
        html.H2("CGN - Interface bateau (V2)"),
        html.P("Objectif: configurer un bateau simplement, sans manipuler directement le YAML."),
        dcc.Interval(id="v2-refresh", interval=250, n_intervals=0, max_intervals=1),
        dcc.Store(id="v2-schema-store", data=blank_schema()),
        dcc.Store(id="v2-sim-schema-store", data=blank_schema()),
        dcc.Store(id="v2-last-yaml", data=""),
        dcc.Store(id="v2-tpl-form-initial", data={}),
        dcc.Store(id="v2-tpl-draft-store", data={}),
        dcc.ConfirmDialog(id="v2-tpl-save-confirm", message="Composant valide. Voulez-vous le sauvegarder ?"),
        dcc.Tabs(
            id="v2-tabs",
            value="prep",
            children=[
                dcc.Tab(
                    label="Preparation",
                    value="prep",
                    children=[
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.H4("1) Bibliotheque de composants"),
                                        html.Label("Nom composant"),
                                        dcc.Input(id="v2-tpl-name", type="text", style={"width": "100%"}),
                                        html.Div(style={"height": "6px"}),
                                        html.Label("Type composant"),
                                        dcc.Dropdown(id="v2-tpl-type", options=TYPE_OPTIONS, value="converter", clearable=False),
                                        html.Div(style={"height": "6px"}),
                                        html.Label("Modele composant"),
                                        dcc.Dropdown(id="v2-tpl-form-key", options=_form_options("converter"), value=_default_form_key("converter"), clearable=False),
                                        html.Div(style={"height": "6px"}),
                                        html.Div(
                                            [
                                                html.Button("Creer", id="v2-tpl-open-modal", n_clicks=0),
                                                html.Button("Supprimer selection", id="v2-tpl-delete", n_clicks=0, style={"marginLeft": "8px"}),
                                            ],
                                            style={"marginTop": "8px"},
                                        ),
                                        html.Div(
                                            id="v2-tpl-modal-overlay",
                                            style={
                                                "display": "none",
                                                "position": "fixed",
                                                "inset": "0",
                                                "backgroundColor": "rgba(0,0,0,0.35)",
                                                "zIndex": "1000",
                                            },
                                            children=[
                                                html.Div(
                                                    style={
                                                        "width": "620px",
                                                        "maxWidth": "92vw",
                                                        "maxHeight": "85vh",
                                                        "overflowY": "auto",
                                                        "backgroundColor": "white",
                                                        "margin": "6vh auto",
                                                        "padding": "14px",
                                                        "borderRadius": "10px",
                                                        "boxShadow": "0 12px 28px rgba(0,0,0,0.22)",
                                                    },
                                                    children=[
                                                        html.H4("Creation composant"),
                                                        html.P("Remplis les champs, puis clique 'Valider'."),
                                                        html.Div(
                                                            id="v2-tpl-form-fields",
                                                            children=_build_form_children(_default_form_key("converter"), {}),
                                                        ),
                                                        html.Details(
                                                            [
                                                                html.Summary("Mode expert (JSON genere)"),
                                                                dcc.Textarea(
                                                                    id="v2-tpl-payload",
                                                                    value=json.dumps(
                                                                        _default_payload_by_type("converter"),
                                                                        ensure_ascii=False,
                                                                        indent=2,
                                                                    ),
                                                                    style={"width": "100%", "height": "120px", "fontFamily": "Consolas, monospace"},
                                                                ),
                                                            ]
                                                        ),
                                                        html.Div(
                                                            [
                                                                html.Button("Valider", id="v2-tpl-validate", n_clicks=0),
                                                                html.Button("Fermer", id="v2-tpl-close-modal", n_clicks=0, style={"marginLeft": "8px"}),
                                                            ],
                                                            style={"marginTop": "10px"},
                                                        ),
                                                    ],
                                                )
                                            ],
                                        ),
                                        html.Div(id="v2-tpl-status", style={"marginTop": "8px"}),
                                        html.Label("Selection composant"),
                                        dcc.Dropdown(id="v2-tpl-select", options=[]),
                                        dash_table.DataTable(
                                            id="v2-tpl-table",
                                            columns=[
                                                {"name": "ID", "id": "id"},
                                                {"name": "Type", "id": "type"},
                                                {"name": "Kind", "id": "kind"},
                                                {"name": "Nom", "id": "nom"},
                                                {"name": "Maj", "id": "modifie_le"},
                                            ],
                                            data=[],
                                            page_size=6,
                                            style_table={"overflowX": "auto"},
                                        ),
                                    ],
                                    style={"width": "34%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px"},
                                ),
                                html.Div(
                                    [
                                        html.H4("2) Assembleur de briques"),
                                        html.Label("Nom du schema"),
                                        dcc.Input(id="v2-schema-name", type="text", value="Schema", style={"width": "100%"}),
                                        html.Div(style={"height": "6px"}),
                                        html.Label("Nom bateau"),
                                        dcc.Input(id="v2-vessel-name", type="text", value="Bateau", style={"width": "100%"}),
                                        html.Div(style={"height": "6px"}),
                                        html.Label("Type bateau"),
                                        dcc.Dropdown(
                                            id="v2-vessel-type",
                                            options=[
                                                {"label": "Diesel-electrique", "value": "DE"},
                                                {"label": "Vapeur", "value": "steam"},
                                                {"label": "Indefini", "value": "undefined"},
                                            ],
                                            value="DE",
                                            clearable=False,
                                        ),
                                        html.Div(style={"height": "6px"}),
                                        html.Label("Pas de simulation dt (s)"),
                                        dcc.Input(id="v2-dt", type="number", value=1.0, min=0.001, step=0.1, style={"width": "100%"}),
                                        html.Div(style={"height": "10px"}),
                                        html.Label("Ajouter une brique depuis la bibliotheque"),
                                        dcc.Dropdown(id="v2-add-template", options=[]),
                                        html.Div(style={"height": "6px"}),
                                        html.Label("ID instance"),
                                        dcc.Input(id="v2-instance-id", type="text", style={"width": "100%"}),
                                        html.Div(
                                            [
                                                html.Button("Ajouter brique", id="v2-add-instance", n_clicks=0),
                                                html.Button("Sauver schema", id="v2-save-schema", n_clicks=0, style={"marginLeft": "8px"}),
                                            ],
                                            style={"marginTop": "8px"},
                                        ),
                                        html.Div(id="v2-schema-status", style={"marginTop": "8px"}),
                                        html.H5("Edition rapide des liaisons"),
                                        dash_table.DataTable(
                                            id="v2-inst-table",
                                            columns=[
                                                {"name": "instance_id", "id": "instance_id", "editable": False},
                                                {"name": "type", "id": "type", "editable": False},
                                                {"name": "kind", "id": "kind", "editable": False},
                                                {"name": "source", "id": "source", "editable": True},
                                                {"name": "bus", "id": "bus", "editable": True},
                                                {"name": "from_bus", "id": "from_bus", "editable": True},
                                                {"name": "to_bus", "id": "to_bus", "editable": True},
                                            ],
                                            data=[],
                                            editable=True,
                                            row_deletable=True,
                                            page_size=8,
                                            style_table={"overflowX": "auto"},
                                        ),
                                        html.H5("Apercu schema"),
                                        Mermaid(id="v2-mermaid", chart="flowchart LR\n  a[no_data]"),
                                    ],
                                    style={"width": "64%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px"},
                                ),
                            ],
                            style={"display": "flex", "gap": "2%", "padding": "8px"},
                        ),
                    ],
                ),
                dcc.Tab(
                    label="Simulation",
                    value="sim",
                    children=[
                        html.Div(
                            [
                                html.H4("3) Simulation bateau"),
                                html.Label("Charger un schema enregistre"),
                                dcc.Dropdown(id="v2-schema-select-sim", options=[]),
                                html.Div(
                                    [
                                        html.Button("Charger schema", id="v2-load-schema-sim", n_clicks=0),
                                        html.Button("Lancer simulation", id="v2-run-sim", n_clicks=0, style={"marginLeft": "8px"}),
                                    ],
                                    style={"marginTop": "8px"},
                                ),
                                html.Div(id="v2-sim-status", style={"marginTop": "8px"}),
                                html.H5("Briques (editable ici sans sauver en DB)"),
                                dash_table.DataTable(
                                    id="v2-sim-inst-table",
                                    columns=[
                                        {"name": "instance_id", "id": "instance_id", "editable": False},
                                        {"name": "type", "id": "type", "editable": False},
                                        {"name": "kind", "id": "kind", "editable": False},
                                        {"name": "source", "id": "source", "editable": True},
                                        {"name": "bus", "id": "bus", "editable": True},
                                        {"name": "from_bus", "id": "from_bus", "editable": True},
                                        {"name": "to_bus", "id": "to_bus", "editable": True},
                                    ],
                                    data=[],
                                    editable=True,
                                    row_deletable=True,
                                    page_size=8,
                                    style_table={"overflowX": "auto"},
                                ),
                                dcc.Graph(id="v2-sim-graph"),
                                html.H5("Apercu YAML genere (mode expert)"),
                                dcc.Textarea(
                                    id="v2-yaml-preview",
                                    readOnly=True,
                                    style={"width": "100%", "height": "220px", "fontFamily": "Consolas, monospace"},
                                ),
                                html.H5("Apercu tabulaire"),
                                dash_table.DataTable(
                                    id="v2-sim-table",
                                    page_size=10,
                                    style_table={"overflowX": "auto"},
                                ),
                            ],
                            style={"padding": "10px"},
                        )
                    ],
                ),
            ],
        ),
        html.Div(style={"height": "120px"}),
    ],
    style={"margin": "16px"},
)


@callback(
    Output("v2-tpl-select", "options"),
    Output("v2-add-template", "options"),
    Output("v2-tpl-table", "data"),
    Output("v2-schema-select-sim", "options"),
    Input("v2-refresh", "n_intervals"),
    Input("v2-tpl-save-confirm", "submit_n_clicks"),
    Input("v2-tpl-delete", "n_clicks"),
    Input("v2-save-schema", "n_clicks"),
)
def refresh_sources(_: int, __: int, ___: int, ____: int):
    tpl_opts = _template_options()
    schema_opts = _schema_options()
    return tpl_opts, tpl_opts, _template_table_rows(), schema_opts


@callback(
    Output("v2-tpl-form-key", "options"),
    Output("v2-tpl-form-key", "value"),
    Output("v2-tpl-form-initial", "data"),
    Input("v2-tpl-type", "value"),
    prevent_initial_call=True,
)
def set_form_for_type(component_type: str):
    opts = _form_options(component_type or "converter")
    value = _default_form_key(component_type or "converter")
    return opts, value, {}


@callback(
    Output("v2-tpl-name", "value"),
    Output("v2-tpl-type", "value"),
    Output("v2-tpl-form-key", "options"),
    Output("v2-tpl-form-key", "value"),
    Output("v2-tpl-form-initial", "data"),
    Output("v2-tpl-payload", "value"),
    Output("v2-tpl-status", "children"),
    Input("v2-tpl-select", "value"),
    prevent_initial_call=True,
)
def load_template(selected_id: int | None):
    if selected_id is None:
        raise PreventUpdate
    t = get_template(int(selected_id))
    if t is None:
        return no_update, no_update, no_update, no_update, no_update, no_update, "Template introuvable."
    payload_text = json.dumps(t["payload"], ensure_ascii=False, indent=2)
    component = t.get("payload", {}).get("component", {})
    ctype = str(t["component_type"])
    form_opts = _form_options(ctype)
    form_key = infer_form_key(ctype, str(t["kind"] or ""))
    if form_key is None:
        form_key = _default_form_key(ctype)
    initial: dict[str, Any] = {}
    if form_key:
        model_cls = model_for_key(form_key)
        if model_cls is not None and isinstance(component, dict):
            try:
                initial = model_cls.from_component(component).model_dump()
            except Exception:  # noqa: BLE001
                initial = {}
    return t["name"], ctype, form_opts, form_key, initial, payload_text, f'Template charge: {t["name"]}'


@callback(
    Output("v2-tpl-form-fields", "children"),
    Output("v2-tpl-payload", "value", allow_duplicate=True),
    Input("v2-tpl-form-key", "value"),
    Input("v2-tpl-form-initial", "data"),
    prevent_initial_call=True,
)
def render_form(form_key: str | None, initial: dict[str, Any] | None):
    fields = _build_form_children(form_key, initial)
    payload_value = no_update
    if form_key:
        model_cls = model_for_key(form_key)
        if model_cls is not None:
            try:
                model_obj = model_cls.model_validate(initial or {})
                payload_value = json.dumps({"component": model_obj.to_component()}, ensure_ascii=False, indent=2)
            except Exception:  # noqa: BLE001
                payload_value = no_update
    return fields, payload_value


@callback(
    Output("v2-tpl-payload", "value", allow_duplicate=True),
    Input({"type": "v2-form-field", "field": ALL}, "value"),
    State({"type": "v2-form-field", "field": ALL}, "id"),
    State("v2-tpl-form-key", "value"),
    prevent_initial_call=True,
)
def sync_payload_from_form(values: list[Any], ids: list[dict[str, str]], form_key: str | None):
    if not form_key:
        raise PreventUpdate
    try:
        _, payload = _payload_from_form(form_key, ids or [], values or [])
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        raise PreventUpdate


@callback(
    Output("v2-tpl-modal-overlay", "style"),
    Input("v2-tpl-open-modal", "n_clicks"),
    Input("v2-tpl-close-modal", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_template_modal(open_clicks: int, close_clicks: int):
    del open_clicks, close_clicks
    trigger = ctx.triggered_id
    if trigger == "v2-tpl-open-modal":
        return {
            "display": "block",
            "position": "fixed",
            "inset": "0",
            "backgroundColor": "rgba(0,0,0,0.35)",
            "zIndex": "1000",
        }
    return {
        "display": "none",
        "position": "fixed",
        "inset": "0",
        "backgroundColor": "rgba(0,0,0,0.35)",
        "zIndex": "1000",
    }


@callback(
    Output("v2-tpl-status", "children", allow_duplicate=True),
    Output("v2-tpl-draft-store", "data"),
    Output("v2-tpl-save-confirm", "displayed"),
    Output("v2-tpl-modal-overlay", "style", allow_duplicate=True),
    Input("v2-tpl-validate", "n_clicks"),
    State("v2-tpl-name", "value"),
    State("v2-tpl-type", "value"),
    State("v2-tpl-form-key", "value"),
    State({"type": "v2-form-field", "field": ALL}, "id"),
    State({"type": "v2-form-field", "field": ALL}, "value"),
    prevent_initial_call=True,
)
def validate_template(
    _: int,
    name: str | None,
    ctype: str | None,
    form_key: str | None,
    field_ids: list[dict[str, str]],
    field_values: list[Any],
):
    try:
        raw_name = str(name or "").strip()
        if not raw_name:
            raise ValueError("Le nom composant est obligatoire.")
        if not form_key:
            raise ValueError("Choisis un modele composant.")
        kind, payload = _payload_from_form(form_key, field_ids or [], field_values or [])
        draft = {
            "name": raw_name,
            "component_type": str(ctype or ""),
            "kind": kind,
            "payload": payload,
        }
        return (
            "Composant valide. Confirmation de sauvegarde ouverte.",
            draft,
            True,
            {
                "display": "none",
                "position": "fixed",
                "inset": "0",
                "backgroundColor": "rgba(0,0,0,0.35)",
                "zIndex": "1000",
            },
        )
    except ValidationError as exc:
        return (
            f"Erreur formulaire: {exc.errors()}",
            no_update,
            False,
            no_update,
        )
    except Exception as exc:  # noqa: BLE001
        return (
            f"Erreur composant: {exc}",
            no_update,
            False,
            no_update,
        )


@callback(
    Output("v2-tpl-status", "children", allow_duplicate=True),
    Output("v2-tpl-select", "value"),
    Input("v2-tpl-save-confirm", "submit_n_clicks"),
    State("v2-tpl-draft-store", "data"),
    prevent_initial_call=True,
)
def save_template_from_confirm(submit_n_clicks: int, draft: dict[str, Any] | None):
    if not submit_n_clicks:
        raise PreventUpdate
    if not isinstance(draft, dict):
        return "Aucun brouillon valide a sauvegarder.", no_update
    try:
        tid = upsert_template(
            name=str(draft.get("name", "")),
            family="General",
            component_type=str(draft.get("component_type", "")),
            kind=str(draft.get("kind", "")),
            payload=draft.get("payload", {}),
        )
        return "Template sauvegarde.", tid
    except Exception as exc:  # noqa: BLE001
        return f"Erreur sauvegarde: {exc}", no_update


@callback(
    Output("v2-tpl-status", "children", allow_duplicate=True),
    Output("v2-tpl-select", "value", allow_duplicate=True),
    Input("v2-tpl-delete", "n_clicks"),
    State("v2-tpl-select", "value"),
    prevent_initial_call=True,
)
def remove_template(_: int, selected_id: int | None):
    if selected_id is None:
        return "Selectionne un template.", no_update
    delete_template(int(selected_id))
    return "Template supprime.", None


@callback(
    Output("v2-schema-store", "data"),
    Output("v2-schema-status", "children"),
    Input("v2-add-instance", "n_clicks"),
    State("v2-add-template", "value"),
    State("v2-instance-id", "value"),
    State("v2-schema-name", "value"),
    State("v2-vessel-name", "value"),
    State("v2-vessel-type", "value"),
    State("v2-dt", "value"),
    State("v2-schema-store", "data"),
    prevent_initial_call=True,
)
def add_instance(
    _: int,
    template_id: int | None,
    instance_id: str | None,
    schema_name: str | None,
    vessel_name: str | None,
    vessel_type: str | None,
    dt: float | None,
    schema: dict[str, Any],
):
    if template_id is None:
        return no_update, "Choisis un composant a ajouter."
    current = dict(schema or blank_schema())
    current["name"] = str(schema_name or "Schema")
    current["vessel_name"] = str(vessel_name or "Bateau")
    current["vessel_type"] = str(vessel_type or "DE")
    current["dt"] = float(dt or 1.0)
    instances = list(current.get("instances", []))
    iid = str(instance_id or "").strip() or f"inst_{len(instances)+1}"
    instances.append({"template_id": int(template_id), "instance_id": iid})
    current["instances"] = instances
    return current, f"Brique ajoutee: {iid}"


@callback(
    Output("v2-schema-store", "data", allow_duplicate=True),
    Output("v2-schema-status", "children", allow_duplicate=True),
    Input("v2-inst-table", "data_timestamp"),
    State("v2-inst-table", "data"),
    State("v2-schema-store", "data"),
    prevent_initial_call=True,
)
def update_instances_from_table(_: int, table_rows: list[dict[str, Any]] | None, schema: dict[str, Any]):
    if table_rows is None:
        raise PreventUpdate
    current = dict(schema or blank_schema())
    old_instances = list(current.get("instances", []))
    by_id = {str(i.get("instance_id", "")): i for i in old_instances}
    new_instances: list[dict[str, Any]] = []
    for r in table_rows:
        iid = str(r.get("instance_id", "")).strip()
        if not iid:
            continue
        base = dict(by_id.get(iid, {"instance_id": iid, "template_id": 0}))
        for key in ("source", "bus", "from_bus", "to_bus"):
            val = str(r.get(key, "") or "").strip()
            base[key] = val if val else None
        new_instances.append(base)
    current["instances"] = new_instances
    return current, "Liaisons mises a jour."


@callback(
    Output("v2-schema-status", "children", allow_duplicate=True),
    Input("v2-save-schema", "n_clicks"),
    State("v2-schema-name", "value"),
    State("v2-schema-store", "data"),
    prevent_initial_call=True,
)
def save_schema(_: int, schema_name: str | None, schema: dict[str, Any]):
    try:
        current = dict(schema or blank_schema())
        current["name"] = str(schema_name or current.get("name", "Schema"))
        upsert_schema(current["name"], current)
        return f'Schema sauvegarde: {current["name"]}'
    except Exception as exc:  # noqa: BLE001
        return f"Erreur schema: {exc}"


@callback(
    Output("v2-mermaid", "chart"),
    Output("v2-inst-table", "data"),
    Output("v2-yaml-preview", "value"),
    Input("v2-schema-store", "data"),
)
def render_schema(schema: dict[str, Any]):
    templates = {int(t["id"]): t for t in list_templates()}
    cfg = build_yaml_config_from_schema(schema or blank_schema(), templates)
    chart = yaml_to_simple_mermaid(cfg)
    rows = _instances_table(schema or blank_schema(), templates)
    return chart, rows, to_yaml_text(cfg)


@callback(
    Output("v2-sim-schema-store", "data"),
    Output("v2-sim-status", "children"),
    Output("v2-sim-inst-table", "data"),
    Input("v2-load-schema-sim", "n_clicks"),
    State("v2-schema-select-sim", "value"),
    prevent_initial_call=True,
)
def load_schema_for_sim(_: int, selected_id: int | None):
    if selected_id is None:
        return no_update, "Selectionne un schema.", no_update
    row = get_schema(int(selected_id))
    if row is None:
        return no_update, "Schema introuvable.", no_update
    schema = row["schema"]
    templates = {int(t["id"]): t for t in list_templates()}
    table_rows = _instances_table(schema, templates)
    return schema, f'Schema charge pour simulation: {row["name"]}', table_rows


@callback(
    Output("v2-sim-schema-store", "data", allow_duplicate=True),
    Input("v2-sim-inst-table", "data_timestamp"),
    State("v2-sim-inst-table", "data"),
    State("v2-sim-schema-store", "data"),
    prevent_initial_call=True,
)
def update_sim_schema_from_table(_: int, rows: list[dict[str, Any]] | None, schema: dict[str, Any]):
    if rows is None:
        raise PreventUpdate
    current = dict(schema or blank_schema())
    old = list(current.get("instances", []))
    by_id = {str(i.get("instance_id", "")): i for i in old}
    new_instances: list[dict[str, Any]] = []
    for r in rows:
        iid = str(r.get("instance_id", "")).strip()
        if not iid:
            continue
        base = dict(by_id.get(iid, {"instance_id": iid, "template_id": 0}))
        for key in ("source", "bus", "from_bus", "to_bus"):
            val = str(r.get(key, "") or "").strip()
            base[key] = val if val else None
        new_instances.append(base)
    current["instances"] = new_instances
    return current


@callback(
    Output("v2-sim-status", "children", allow_duplicate=True),
    Output("v2-sim-graph", "figure"),
    Output("v2-sim-table", "data"),
    Output("v2-sim-table", "columns"),
    Output("v2-yaml-preview", "value", allow_duplicate=True),
    Input("v2-run-sim", "n_clicks"),
    State("v2-sim-schema-store", "data"),
    prevent_initial_call=True,
)
def run_sim(_: int, schema: dict[str, Any]):
    try:
        templates = {int(t["id"]): t for t in list_templates()}
        cfg = build_yaml_config_from_schema(schema or blank_schema(), templates)
        out = run_simulation_from_cfg(cfg)
        fig = _profiles_plot(out.dataframe)
        data = out.dataframe.head(200).to_dict("records")
        cols = [{"name": c, "id": c} for c in out.dataframe.columns]
        return (
            f"Simulation OK: {out.n_rows} lignes, {len(out.columns)} colonnes.",
            fig,
            data,
            cols,
            to_yaml_text(cfg),
        )
    except Exception as exc:  # noqa: BLE001
        fig = go.Figure()
        fig.update_layout(title="Simulation en echec")
        return f"Erreur simulation: {exc}", fig, [], [], ""


if __name__ == "__main__":
    app.run(debug=True)
