"""
Prototype local-first pour creation de composants via dash-pydantic-form.

Objectif:
- formulaire dynamique par type + modele;
- validation Pydantic;
- sortie locale (store) sans ecriture DB.
"""

from __future__ import annotations

import json
from typing import Any

from dash import Dash, Input, Output, State, callback, dash_table, dcc, html, no_update
import dash_mantine_components as dmc
from pydantic import BaseModel, ValidationError

from dash_pydantic_form import ModelForm

from idees_basemodel import (
    ConstantEtaConverter,
    ForceAndSpeedToPowerAdapter,
    SpeedToForcePoly,
    SpeedToPowerPolyAdapter,
    VariableEtaConverter,
)


AIO_ID = "v2-local-form"
FORM_ID = "main"


def _first_doc_line(model_cls: type[BaseModel]) -> str:
    doc = (model_cls.__doc__ or "").strip()
    if not doc:
        return model_cls.__name__
    return doc.splitlines()[0].strip()


MODEL_SPECS: dict[str, dict[str, Any]] = {
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
}


TYPE_OPTIONS = [
    {"label": "Profil (signal entree)", "value": "profile"},
    {"label": "Adaptateur (transformateur signal)", "value": "adapter"},
    {"label": "Convertisseur puissance (watt)", "value": "converter"},
    {"label": "Stockage energie", "value": "storage"},
]


def _model_options(component_type: str) -> list[dict[str, str]]:
    opts: list[dict[str, str]] = []
    for key, spec in MODEL_SPECS.items():
        if spec["component_type"] == component_type:
            model_cls = spec["model"]
            opts.append({"label": _first_doc_line(model_cls), "value": key})
    return opts


def _default_model_key(component_type: str) -> str | None:
    opts = _model_options(component_type)
    if not opts:
        return None
    return str(opts[0]["value"])


def _to_component_payload(model_key: str, form_data: dict[str, Any]) -> dict[str, Any]:
    spec = MODEL_SPECS[model_key]
    kind = str(spec["kind"])
    ctype = str(spec["component_type"])
    model_cls = spec["model"]
    obj = model_cls.model_validate(form_data)
    data = obj.model_dump()

    if model_key == "converter.constant_eta":
        component = {
            "id": data["id"],
            "kind": "constant_eta",
            "from_bus": data.get("from_bus"),
            "to_bus": data.get("to_bus"),
            "params": {"eta": data["eta"]},
        }
    elif model_key == "converter.variable_eta":
        component = {
            "id": data["id"],
            "kind": "variable_eta",
            "from_bus": data.get("from_bus"),
            "to_bus": data.get("to_bus"),
            "params": {
                "eta_default": 1.0,
                "eta_source": data["eta_source"],
            },
        }
    elif model_key == "adapter.speed_to_power_poly":
        component = {
            "id": data["id"],
            "kind": "speed_to_power_poly",
            "source": data["source"],
            "unit_in": data.get("unit_in", "m/s"),
            "unit_out": data.get("unit_out", "W"),
            "params": {"coeffs": data["coeffs"]},
        }
    elif model_key == "adapter.force_and_speed_to_power":
        component = {
            "id": data["id"],
            "kind": "force_and_speed_to_power",
            "source": "",
            "unit_in": "",
            "unit_out": data.get("unit_out", "W"),
            "params": {
                "force_source": data["force_source"],
                "speed_source": data["speed_source"],
                "force_unit_in": data.get("force_unit_in", "N"),
                "speed_unit_in": data.get("speed_unit_in", "m/s"),
                "clip_min": 0.0,
            },
        }
    elif model_key == "adapter.speed_to_force_poly":
        component = {
            "id": data["id"],
            "kind": "speed_to_force_poly",
            "source": data["source"],
            "unit_in": data.get("unit_in", "m/s"),
            "unit_out": data.get("unit_out", "N"),
            "params": {"coeffs": data["coeffs"]},
        }
    else:
        raise ValueError(f"Modele non supporte: {model_key}")

    return {
        "template_name": data["id"],
        "component_type": ctype,
        "kind": kind,
        "payload": {"component": component},
    }


app = Dash(
    __name__,
    external_stylesheets=[
        "https://unpkg.com/@mantine/dates@7/styles.css",
        "https://unpkg.com/@mantine/code-highlight@7/styles.css",
        "https://unpkg.com/@mantine/charts@7/styles.css",
        "https://unpkg.com/@mantine/carousel@7/styles.css",
        "https://unpkg.com/@mantine/notifications@7/styles.css",
        "https://unpkg.com/@mantine/nprogress@7/styles.css",
    ],
)
app.title = "CGN V2 - Proto Formulaire Local"

app.layout = dmc.MantineProvider(
    dmc.Container(
        [
            html.H3("Prototype formulaire local (dash-pydantic-form)"),
            html.P("Validation locale puis ajout a une bibliotheque locale (pas de DB)."),
            dcc.Store(id="v2-local-components", data=[]),
            html.Div(
                [
                    html.Label("Type composant"),
                    dcc.Dropdown(id="v2-local-type", options=TYPE_OPTIONS, value="converter", clearable=False),
                    html.Div(style={"height": "8px"}),
                    html.Label("Modele composant"),
                    dcc.Dropdown(id="v2-local-model", options=_model_options("converter"), value=_default_model_key("converter"), clearable=False),
                    html.Div(style={"height": "10px"}),
                    html.Details(
                        [
                            html.Summary("Formulaire composant"),
                            html.Div(id="v2-local-form-container"),
                        ],
                        open=True,
                    ),
                    html.Div(
                        [
                            html.Button("Valider formulaire", id="v2-local-validate", n_clicks=0),
                            html.Button("Ajouter en local", id="v2-local-add", n_clicks=0, style={"marginLeft": "8px"}),
                        ],
                        style={"marginTop": "10px"},
                    ),
                    html.Div(id="v2-local-status", style={"marginTop": "8px"}),
                ],
                style={"width": "44%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px"},
            ),
            html.Div(style={"height": "10px"}),
            html.Div(
                [
                    html.H4("Composants locaux"),
                    dash_table.DataTable(
                        id="v2-local-table",
                        columns=[
                            {"name": "Nom", "id": "template_name"},
                            {"name": "Type", "id": "component_type"},
                            {"name": "Kind", "id": "kind"},
                        ],
                        data=[],
                        row_deletable=True,
                        editable=False,
                        page_size=8,
                        style_table={"overflowX": "auto"},
                    ),
                    html.H5("Sortie locale JSON"),
                    dcc.Textarea(id="v2-local-json", readOnly=True, style={"width": "100%", "height": "240px", "fontFamily": "Consolas, monospace"}),
                ],
                style={"border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px"},
            ),
        ],
        fluid=True,
        style={"margin": "16px"},
    )
)


@callback(
    Output("v2-local-model", "options"),
    Output("v2-local-model", "value"),
    Input("v2-local-type", "value"),
)
def update_model_options(component_type: str):
    opts = _model_options(component_type or "converter")
    return opts, _default_model_key(component_type or "converter")


@callback(
    Output("v2-local-form-container", "children"),
    Input("v2-local-model", "value"),
)
def render_dynamic_form(model_key: str | None):
    if not model_key or model_key not in MODEL_SPECS:
        return html.Div("Aucun modele pour ce type.")
    model_cls = MODEL_SPECS[model_key]["model"]
    return ModelForm(model_cls, AIO_ID, FORM_ID, debounce=200)


@callback(
    Output("v2-local-status", "children"),
    Input("v2-local-validate", "n_clicks"),
    State("v2-local-model", "value"),
    State(ModelForm.ids.main(AIO_ID, FORM_ID), "data"),
    prevent_initial_call=True,
)
def validate_form(_: int, model_key: str | None, form_data: dict[str, Any] | None):
    if not model_key:
        return "Choisis un modele."
    if not isinstance(form_data, dict):
        return "Formulaire vide."
    try:
        _to_component_payload(model_key, form_data)
        return "Validation OK. Tu peux ajouter en local."
    except ValidationError as exc:
        return f"Erreur validation: {exc.errors()}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur: {exc}"


@callback(
    Output("v2-local-components", "data"),
    Output("v2-local-status", "children", allow_duplicate=True),
    Input("v2-local-add", "n_clicks"),
    State("v2-local-model", "value"),
    State(ModelForm.ids.main(AIO_ID, FORM_ID), "data"),
    State("v2-local-components", "data"),
    prevent_initial_call=True,
)
def add_local_component(_: int, model_key: str | None, form_data: dict[str, Any] | None, items: list[dict[str, Any]] | None):
    if not model_key:
        return no_update, "Choisis un modele."
    if not isinstance(form_data, dict):
        return no_update, "Formulaire vide."
    try:
        payload = _to_component_payload(model_key, form_data)
        current = list(items or [])
        current.append(payload)
        return current, f"Composant local ajoute: {payload['template_name']}"
    except ValidationError as exc:
        return no_update, f"Erreur validation: {exc.errors()}"
    except Exception as exc:  # noqa: BLE001
        return no_update, f"Erreur ajout local: {exc}"


@callback(
    Output("v2-local-table", "data"),
    Output("v2-local-json", "value"),
    Input("v2-local-components", "data"),
)
def render_local_items(items: list[dict[str, Any]] | None):
    rows = list(items or [])
    return rows, json.dumps(rows, ensure_ascii=False, indent=2)


@callback(
    Output("v2-local-components", "data", allow_duplicate=True),
    Input("v2-local-table", "data_timestamp"),
    State("v2-local-table", "data"),
    prevent_initial_call=True,
)
def sync_local_store_from_table(_: int, rows: list[dict[str, Any]] | None):
    return list(rows or [])


if __name__ == "__main__":
    app.run(debug=True)
