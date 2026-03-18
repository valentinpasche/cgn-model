"""
UI V2 orientee metier bateau (sans YAML expose par defaut).
"""

from __future__ import annotations

import json
from typing import Any, get_args, get_origin

from dash import ALL, Dash, Input, Output, State, callback, ctx, dash_table, dcc, html, no_update
from dash.exceptions import PreventUpdate
from dash_extensions import Mermaid
import dash_mantine_components as dmc
import plotly.graph_objects as go
from pydantic import ValidationError
from dash_pydantic_form import ModelForm, fields

from components_basemodel import (
    ConstantEtaConverter,
    ForceAndSpeedToPowerAdapter,
    SpeedToForcePoly,
    SpeedToPowerPolyAdapter,
    VariableEtaConverter,
)
from models.component_forms import forms_for_component_type, infer_form_key, model_for_key
from services.assembler import blank_schema, build_yaml_config_from_schema, to_yaml_text, yaml_to_simple_mermaid
from services.simulation import run_simulation_from_cfg
from services.storage import (
    delete_template,
    get_schema,
    get_template,
    get_template_by_name,
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


V2M_AIO = "v2m-form"
V2M_FORM = "main"

V2M_MODEL_SPECS: dict[str, dict[str, Any]] = {
    "converter.constant_eta": {"component_type": "converter", "kind": "constant_eta", "model": ConstantEtaConverter},
    "converter.variable_eta": {"component_type": "converter", "kind": "variable_eta", "model": VariableEtaConverter},
    "adapter.speed_to_power_poly": {"component_type": "adapter", "kind": "speed_to_power_poly", "model": SpeedToPowerPolyAdapter},
    "adapter.force_and_speed_to_power": {"component_type": "adapter", "kind": "force_and_speed_to_power", "model": ForceAndSpeedToPowerAdapter},
    "adapter.speed_to_force_poly": {"component_type": "adapter", "kind": "speed_to_force_poly", "model": SpeedToForcePoly},
}


def _v2m_model_options(component_type: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for key, spec in V2M_MODEL_SPECS.items():
        if spec["component_type"] == component_type:
            model_cls = spec["model"]
            doc = (model_cls.__doc__ or "").strip().splitlines()
            label = doc[0].strip() if doc else model_cls.__name__
            out.append({"label": label, "value": key})
    return out


def _v2m_default_model_key(component_type: str) -> str | None:
    opts = _v2m_model_options(component_type)
    if not opts:
        return None
    return str(opts[0]["value"])


def _v2m_fields_repr(model_key: str) -> dict[str, Any]:
    if model_key in {"adapter.speed_to_power_poly", "adapter.speed_to_force_poly"}:
        return {
            "coeffs": fields.List(
                render_type="scalar",
                n_cols="var(--pydf-form-cols)",
                wrapper_kwargs={"style": {"gridTemplateColumns": "repeat(5, minmax(0, 1fr))"}},
            )
        }
    return {}


def _v2m_render_form(model_key: str | None, seed: dict[str, Any] | None = None):
    if not model_key or model_key not in V2M_MODEL_SPECS:
        return html.Div("Aucun modele pour ce type.")
    model_cls = V2M_MODEL_SPECS[model_key]["model"]
    item: Any = model_cls
    if isinstance(seed, dict) and seed:
        try:
            item = model_cls.model_validate(seed)
        except Exception:  # noqa: BLE001
            # Prefill tolerant: keep only known fields when seed is partial/mixed.
            safe_seed = {k: v for k, v in seed.items() if k in model_cls.model_fields}
            item = model_cls.model_construct(**safe_seed)
    return ModelForm(item, V2M_AIO, V2M_FORM, debounce=200, form_cols=10, fields_repr=_v2m_fields_repr(model_key))


def _v2m_validate_data(model_key: str, form_data: dict[str, Any]) -> dict[str, Any]:
    model_cls = V2M_MODEL_SPECS[model_key]["model"]
    obj = model_cls.model_validate(form_data)
    return obj.model_dump(exclude_none=True)


def _v2m_payload_from_data(model_key: str, raw: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    spec = V2M_MODEL_SPECS[model_key]
    ctype = str(spec["component_type"])
    kind = str(spec["kind"])
    if model_key == "converter.constant_eta":
        component = {"id": raw["id"], "kind": kind, "from_bus": raw.get("from_bus"), "to_bus": raw.get("to_bus"), "params": {"eta": raw["eta"]}}
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
    else:
        raise ValueError(f"Modele non supporte: {model_key}")
    return ctype, kind, {"component": component}


def _v2m_seed_from_template(component_type: str, kind: str, payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    key = f"{component_type}.{kind}"
    if key not in V2M_MODEL_SPECS:
        return None, {}
    c = payload.get("component", {}) if isinstance(payload, dict) else {}
    p = c.get("params", {}) if isinstance(c.get("params"), dict) else {}
    if key == "converter.constant_eta":
        return key, {"id": c.get("id", ""), "from_bus": c.get("from_bus"), "to_bus": c.get("to_bus"), "eta": p.get("eta", 1.0)}
    if key == "converter.variable_eta":
        return key, {"id": c.get("id", ""), "from_bus": c.get("from_bus"), "to_bus": c.get("to_bus"), "eta_source": p.get("eta_source", "")}
    if key == "adapter.speed_to_power_poly":
        return key, {"id": c.get("id", ""), "source": c.get("source", ""), "unit_in": c.get("unit_in", "m/s"), "unit_out": c.get("unit_out", "W"), "coeffs": p.get("coeffs", [])}
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
        return key, {"id": c.get("id", ""), "source": c.get("source", ""), "unit_in": c.get("unit_in", "m/s"), "unit_out": c.get("unit_out", "N"), "coeffs": p.get("coeffs", [])}
    return None, {}


def _v2m_local_table_rows(local_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _v2m_db_table_rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in list_templates():
        key = f'{r.get("component_type", "")}.{r.get("kind", "")}'
        if key not in V2M_MODEL_SPECS:
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


init_db()
app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "CGN UI V2 - Bateau"

app.layout = dmc.MantineProvider(
    html.Div(
        [
            html.H2("CGN - Interface bateau (V2)"),
            html.P("Objectif: configurer un bateau simplement, sans manipuler directement le YAML."),
            dcc.Interval(id="v2-refresh", interval=250, n_intervals=0, max_intervals=1),
            dcc.Store(id="v2-schema-store", data=blank_schema()),
            dcc.Store(id="v2-sim-schema-store", data=blank_schema()),
            dcc.Store(id="v2-last-yaml", data=""),
            dcc.Store(id="v2m-local-components", data=[]),
            dcc.Store(id="v2m-form-seed", data={}),
            dcc.Store(id="v2m-pending-save", data={}),
            dcc.Store(id="v2-tpl-form-initial", data={}),
            dcc.Store(id="v2-tpl-draft-store", data={}),
            dcc.ConfirmDialog(id="v2-tpl-save-confirm", message="Composant valide. Voulez-vous le sauvegarder ?"),
            dmc.Modal(
                id="v2m-update-modal",
                title="Confirmation mise a jour",
                opened=False,
                children=[
                    html.P("Ce nom existe deja. Voulez-vous le mettre a jour ?"),
                    html.Div(
                        [
                            html.Button("Oui, mettre a jour", id="v2m-update-yes", n_clicks=0),
                            html.Button("Annuler", id="v2m-update-no", n_clicks=0, style={"marginLeft": "8px"}),
                        ],
                        style={"marginTop": "8px"},
                    ),
                ],
            ),
            dmc.Modal(
                id="v2m-delete-modal",
                title="Confirmation suppression",
                opened=False,
                children=[
                    html.P("Voulez-vous vraiment supprimer ce composant ?"),
                    html.Div(
                        [
                            html.Button("Oui, supprimer", id="v2m-delete-yes", n_clicks=0),
                            html.Button("Annuler", id="v2m-delete-no", n_clicks=0, style={"marginLeft": "8px"}),
                        ],
                        style={"marginTop": "8px"},
                    ),
                ],
            ),
            dcc.Tabs(
            id="v2-tabs",
            value="prep",
            children=[
                dcc.Tab(
                    label="Preparation",
                    value="prep",
                    children=[
                        dmc.MantineProvider(
                            html.Div(
                                [
                                    html.H4("0) Gestion composants (nouveau)"),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Label("Type composant"),
                                                    dcc.Dropdown(id="v2m-type", options=TYPE_OPTIONS, value="converter", clearable=False),
                                                    html.Div(style={"height": "8px"}),
                                                    html.Label("Modele composant"),
                                                    dcc.Dropdown(id="v2m-model", options=_v2m_model_options("converter"), value=_v2m_default_model_key("converter"), clearable=False),
                                                    html.Div(style={"height": "10px"}),
                                                    html.Div(id="v2m-form-container", children=_v2m_render_form(_v2m_default_model_key("converter"), {})),
                                                    html.Div(
                                                        [
                                                            html.Button("Valider", id="v2m-validate", n_clicks=0),
                                                            html.Button("Sauvegarder", id="v2m-save", n_clicks=0, style={"marginLeft": "8px"}),
                                                        ],
                                                        style={"marginTop": "10px"},
                                                    ),
                                                    html.Div(
                                                        id="v2m-save-choice",
                                                        style={"display": "none", "marginTop": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"},
                                                        children=[
                                                            html.Span("Sauvegarder en: "),
                                                            html.Button("Local", id="v2m-save-local", n_clicks=0, style={"marginLeft": "8px"}),
                                                            html.Button("DB", id="v2m-save-db", n_clicks=0, style={"marginLeft": "8px"}),
                                                            html.Button("Annuler", id="v2m-save-cancel", n_clicks=0, style={"marginLeft": "8px"}),
                                                        ],
                                                    ),
                                                    html.Div(id="v2m-status", style={"marginTop": "8px"}),
                                                ],
                                                style={"width": "49%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px"},
                                            ),
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            dcc.Dropdown(
                                                                id="v2m-select",
                                                                options=[],
                                                                placeholder="Selectionner un composant",
                                                                style={"width": "100%"},
                                                            ),
                                                            html.Div(
                                                                [
                                                            html.Button("Charger, Editer le formulaire", id="v2m-load-edit", n_clicks=0),
                                                                    html.Button("Supprimer", id="v2m-delete", n_clicks=0, style={"marginLeft": "8px"}),
                                                                ],
                                                                style={"marginTop": "8px"},
                                                            ),
                                                        ],
                                                        style={"marginBottom": "8px"},
                                                    ),
                                                    html.Label("Composants locaux + DB"),
                                                    dash_table.DataTable(
                                                        id="v2m-components-table",
                                                        columns=[
                                                            {"name": "Nom", "id": "name"},
                                                            {"name": "Type", "id": "component_type"},
                                                            {"name": "Kind", "id": "kind"},
                                                            {"name": "Statut", "id": "status"},
                                                        ],
                                                        data=[],
                                                        page_size=10,
                                                        style_table={"overflowX": "auto"},
                                                    ),
                                                ],
                                                style={"width": "49%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px"},
                                            ),
                                        ],
                                        style={"display": "flex", "gap": "2%"},
                                    ),
                                ],
                                style={"padding": "8px"},
                            )
                        ),
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
                                    style={"display": "none"},
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
)


@callback(
    Output("v2m-components-table", "data"),
    Input("v2-refresh", "n_intervals"),
    Input("v2m-local-components", "data"),
    Input("v2m-update-yes", "n_clicks"),
    Input("v2m-delete-yes", "n_clicks"),
    Input("v2m-save-db", "n_clicks"),
)
def v2m_refresh_table(_: int, local_items: list[dict[str, Any]] | None, __: int, ___: int, ____: int):
    return _v2m_local_table_rows(list(local_items or [])) + _v2m_db_table_rows()


@callback(
    Output("v2m-select", "options"),
    Input("v2m-components-table", "data"),
)
def v2m_selector_options(rows: list[dict[str, Any]] | None):
    out: list[dict[str, str]] = []
    for r in (rows or []):
        name = str(r.get("name", ""))
        scope = str(r.get("_scope", ""))
        status = str(r.get("status", ""))
        if not name or not scope:
            continue
        out.append({"label": f"{name} [{status}]", "value": f"{scope}|{name}"})
    return out


@callback(
    Output("v2m-model", "options"),
    Output("v2m-model", "value"),
    Input("v2m-type", "value"),
)
def v2m_update_model_options(component_type: str):
    opts = _v2m_model_options(component_type or "converter")
    return opts, _v2m_default_model_key(component_type or "converter")


@callback(
    Output("v2m-form-container", "children"),
    Input("v2m-model", "value"),
    Input("v2m-form-seed", "data"),
)
def v2m_render_form(model_key: str | None, seed: dict[str, Any] | None):
    return _v2m_render_form(model_key, seed if isinstance(seed, dict) else {})


@callback(
    Output("v2m-type", "value", allow_duplicate=True),
    Output("v2m-model", "value", allow_duplicate=True),
    Output("v2m-form-seed", "data", allow_duplicate=True),
    Output("v2m-status", "children", allow_duplicate=True),
    Input("v2m-load-edit", "n_clicks"),
    State("v2m-components-table", "data"),
    State("v2m-local-components", "data"),
    State("v2m-select", "value"),
    prevent_initial_call=True,
)
def v2m_load_edit(_: int, table_rows: list[dict[str, Any]] | None, local_items: list[dict[str, Any]] | None, selected_value: str | None):
    if not table_rows:
        return no_update, no_update, no_update, "Selectionne un composant dans le tableau."
    row = None
    if selected_value and "|" in selected_value:
        scope, name = selected_value.split("|", 1)
        for r in table_rows:
            if str(r.get("_scope", "")) == scope and str(r.get("name", "")) == name:
                row = r
                break
    if row is None:
        return no_update, no_update, no_update, "Selection invalide."
    ctype = str(row.get("component_type", ""))
    kind = str(row.get("kind", ""))
    if str(row.get("_scope", "")) == "local":
        local_map = {(str(it.get("name", "")), str(it.get("component_type", "")), str(it.get("kind", ""))): it for it in (local_items or [])}
        it = local_map.get((str(row.get("name", "")), ctype, kind), {})
        seed = it.get("data", {}) if isinstance(it, dict) else {}
        model_key = f"{ctype}.{kind}"
    else:
        t = get_template_by_name(str(row.get("name", "")))
        if t is None:
            return no_update, no_update, no_update, "Template DB introuvable."
        model_key, seed = _v2m_seed_from_template(ctype, kind, t.get("payload", {}))
        if model_key is None:
            return no_update, no_update, no_update, "Type/Kind non supporte par ce formulaire."
    return ctype, model_key, seed, f"Edition chargee: {row.get('name', '')}"


@callback(
    Output("v2m-status", "children"),
    Input("v2m-validate", "n_clicks"),
    State("v2m-model", "value"),
    State(ModelForm.ids.main(V2M_AIO, V2M_FORM), "data"),
    State("v2m-components-table", "data"),
    prevent_initial_call=True,
)
def v2m_validate(_: int, model_key: str | None, form_data: dict[str, Any] | None, rows: list[dict[str, Any]] | None):
    if not model_key:
        return "Choisis un modele."
    if not isinstance(form_data, dict):
        return "Formulaire vide."
    try:
        raw = _v2m_validate_data(model_key, form_data)
        name = str(raw.get("id", "")).strip()
        if not name:
            return "Erreur validation: nom requis."
        all_names = {str(r.get("name", "")).strip() for r in (rows or [])}
        if name in all_names:
            return f"Attention: le nom '{name}' existe deja."
        return "Validation OK."
    except ValidationError as exc:
        return f"Erreur validation: {exc.errors()}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur: {exc}"


@callback(
    Output("v2m-save-choice", "style"),
    Input("v2m-save", "n_clicks"),
    Input("v2m-save-cancel", "n_clicks"),
    Input("v2m-save-local", "n_clicks"),
    Input("v2m-save-db", "n_clicks"),
    prevent_initial_call=True,
)
def v2m_toggle_save_choice(_: int, __: int, ___: int, ____: int):
    trig = ctx.triggered_id
    if trig == "v2m-save":
        return {"display": "block", "marginTop": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"}
    return {"display": "none", "marginTop": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"}


@callback(
    Output("v2m-local-components", "data"),
    Output("v2m-status", "children", allow_duplicate=True),
    Output("v2m-pending-save", "data"),
    Output("v2m-update-modal", "opened"),
    Input("v2m-save-local", "n_clicks"),
    Input("v2m-save-db", "n_clicks"),
    State("v2m-model", "value"),
    State(ModelForm.ids.main(V2M_AIO, V2M_FORM), "data"),
    State("v2m-local-components", "data"),
    prevent_initial_call=True,
)
def v2m_save_component(local_clicks: int, db_clicks: int, model_key: str | None, form_data: dict[str, Any] | None, local_items: list[dict[str, Any]] | None):
    del local_clicks, db_clicks
    target = "db" if ctx.triggered_id == "v2m-save-db" else "local"
    if not model_key:
        return no_update, "Choisis un modele.", no_update, False
    if not isinstance(form_data, dict):
        return no_update, "Formulaire vide.", no_update, False
    try:
        raw = _v2m_validate_data(model_key, form_data)
        name = str(raw.get("id", "")).strip()
        ctype, kind, payload = _v2m_payload_from_data(model_key, raw)
        if not name:
            return no_update, "Nom requis.", no_update, False
        if target == "local":
            exists = any(str(it.get("name", "")) == name for it in (local_items or []))
        else:
            exists = get_template_by_name(name) is not None
        pending = {"target": target, "name": name, "component_type": ctype, "kind": kind, "payload": payload, "raw": raw, "model_key": model_key}
        if exists:
            return no_update, f"Le nom '{name}' existe deja. Confirmation requise.", pending, True
        if target == "local":
            current = list(local_items or [])
            current.append({"name": name, "component_type": ctype, "kind": kind, "data": raw})
            return current, f"Composant local sauvegarde: {name}", {}, False
        upsert_template(name=name, family="General", component_type=ctype, kind=kind, payload=payload)
        return no_update, f"Composant sauvegarde en DB: {name}", {}, False
    except ValidationError as exc:
        return no_update, f"Erreur validation: {exc.errors()}", no_update, False
    except Exception as exc:  # noqa: BLE001
        return no_update, f"Erreur sauvegarde: {exc}", no_update, False


@callback(
    Output("v2m-local-components", "data", allow_duplicate=True),
    Output("v2m-status", "children", allow_duplicate=True),
    Output("v2m-pending-save", "data", allow_duplicate=True),
    Output("v2m-update-modal", "opened", allow_duplicate=True),
    Input("v2m-update-yes", "n_clicks"),
    State("v2m-pending-save", "data"),
    State("v2m-local-components", "data"),
    prevent_initial_call=True,
)
def v2m_confirm_update(_: int, pending: dict[str, Any] | None, local_items: list[dict[str, Any]] | None):
    if not isinstance(pending, dict) or not pending:
        return no_update, "Aucune mise a jour en attente.", {}, False
    target = str(pending.get("target", ""))
    name = str(pending.get("name", ""))
    if target == "local":
        current = [it for it in list(local_items or []) if str(it.get("name", "")) != name]
        current.append(
            {
                "name": name,
                "component_type": str(pending.get("component_type", "")),
                "kind": str(pending.get("kind", "")),
                "data": pending.get("raw", {}),
            }
        )
        return current, f"Composant local mis a jour: {name}", {}, False
    upsert_template(
        name=name,
        family="General",
        component_type=str(pending.get("component_type", "")),
        kind=str(pending.get("kind", "")),
        payload=pending.get("payload", {}),
    )
    return no_update, f"Composant DB mis a jour: {name}", {}, False


@callback(
    Output("v2m-delete-modal", "opened"),
    Output("v2m-status", "children", allow_duplicate=True),
    Input("v2m-delete", "n_clicks"),
    State("v2m-select", "value"),
    prevent_initial_call=True,
)
def v2m_request_delete(_: int, selected_value: str | None):
    if not selected_value:
        return False, "Selectionne un composant a supprimer."
    return True, "Confirmation suppression ouverte."


@callback(
    Output("v2m-local-components", "data", allow_duplicate=True),
    Output("v2m-status", "children", allow_duplicate=True),
    Output("v2m-delete-modal", "opened", allow_duplicate=True),
    Input("v2m-delete-yes", "n_clicks"),
    State("v2m-components-table", "data"),
    State("v2m-local-components", "data"),
    State("v2m-select", "value"),
    prevent_initial_call=True,
)
def v2m_confirm_delete(_: int, rows: list[dict[str, Any]] | None, local_items: list[dict[str, Any]] | None, selected_value: str | None):
    if not rows:
        return no_update, "Aucune selection a supprimer.", False
    row = None
    if selected_value and "|" in selected_value:
        scope, name = selected_value.split("|", 1)
        for r in rows:
            if str(r.get("_scope", "")) == scope and str(r.get("name", "")) == name:
                row = r
                break
    if row is None:
        return no_update, "Aucune selection a supprimer.", False
    name = str(row.get("name", ""))
    scope = str(row.get("_scope", ""))
    if scope == "local":
        current = [it for it in list(local_items or []) if str(it.get("name", "")) != name]
        return current, f"Composant local supprime: {name}", False
    t = get_template_by_name(name)
    if t is None:
        return no_update, "Template DB introuvable.", False
    delete_template(int(t["id"]))
    return no_update, f"Composant DB supprime: {name}", False


@callback(
    Output("v2m-update-modal", "opened", allow_duplicate=True),
    Input("v2m-update-no", "n_clicks"),
    prevent_initial_call=True,
)
def v2m_cancel_update(_: int):
    return False


@callback(
    Output("v2m-delete-modal", "opened", allow_duplicate=True),
    Input("v2m-delete-no", "n_clicks"),
    prevent_initial_call=True,
)
def v2m_cancel_delete(_: int):
    return False

@callback(
    Output("v2-tpl-select", "options"),
    Output("v2-add-template", "options"),
    Output("v2-tpl-table", "data"),
    Output("v2-schema-select-sim", "options"),
    Input("v2-refresh", "n_intervals"),
    Input("v2-tpl-save-confirm", "submit_n_clicks"),
    Input("v2-tpl-delete", "n_clicks"),
    Input("v2-save-schema", "n_clicks"),
    Input("v2m-save-db", "n_clicks"),
    Input("v2m-update-yes", "n_clicks"),
    Input("v2m-delete-yes", "n_clicks"),
)
def refresh_sources(_: int, __: int, ___: int, ____: int, _____: int, ______: int, _______: int):
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
    Output("v2-tpl-type", "value", allow_duplicate=True),
    Output("v2-tpl-form-key", "options", allow_duplicate=True),
    Output("v2-tpl-form-key", "value", allow_duplicate=True),
    Output("v2-tpl-form-initial", "data", allow_duplicate=True),
    Output("v2-tpl-payload", "value", allow_duplicate=True),
    Output("v2-tpl-status", "children", allow_duplicate=True),
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
