"""
Onglet bibliotheque: configurations completes + templates composants.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
import re

from dash import Input, Output, State, callback, ctx, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate

from cgn_model.web_mvp.services.db import (
    delete_component_template,
    delete_vessel_config,
    get_component_template,
    get_component_template_by_name,
    get_vessel_config,
    get_vessel_config_by_name,
    list_component_templates,
    list_vessel_configs,
    upsert_component_template,
    upsert_vessel_config,
)
from cgn_model.web_mvp.services.default_yaml import load_default_yaml

register_page(__name__, path="/library", name="Bibliotheque")


COMPONENT_TYPE_OPTIONS = [
    {"label": "Profile", "value": "profile"},
    {"label": "Adapter", "value": "adapter"},
    {"label": "Input", "value": "input"},
    {"label": "Converter", "value": "converter"},
    {"label": "Storage", "value": "storage"},
]


def _load_docs_markdown() -> str:
    """
    Charge la doc YAML projet pour l'afficher en aide rapide dans la bibliotheque.
    """
    try:
        root = Path(__file__).resolve().parents[4]
        guide_path = root / "docs" / "script_guide.md"
        if guide_path.exists():
            yaml_guide = guide_path.read_text(encoding="utf-8")
        else:
            yaml_guide = resources.files("cgn_model.web_mvp").joinpath(
                "data", "script_guide_embedded.md"
            ).read_text(encoding="utf-8")

        # Evite que des annotations de type comme `list[float]` soient lues comme des liens Markdown.
        yaml_guide = re.sub(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\[([^\]\n]+)\](?!\()",
            r"`\1[\2]`",
            yaml_guide,
        )
        intro = (
            "## Aide rapide templates\n\n"
            "Documentation source:\n"
            "- `docs/index.md`\n"
            "- `docs/script_guide.md`\n"
            "- `docs/navigation_guide.md`\n"
            "- `docs/example_script.md`\n\n"
            "En installation standard, cette aide est une copie embarquee de `docs/script_guide.md`.\n\n"
            "---\n\n"
        )
        return intro + yaml_guide
    except Exception as exc:  # noqa: BLE001
        return f"## Aide indisponible\nErreur de chargement docs: `{exc}`"


def _default_payload_for_component_type(component_type: str) -> dict:
    """
    Retourne un modele JSON minimal selon le type de composant.
    """
    if component_type == "profile":
        return {
            "component": {
                "id": "",
                "kind": "constant",
                "unit": "W",
                "value": 0.0,
            }
        }
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
    if component_type == "input":
        return {
            "component": {
                "id": "",
                "source": "",
                "bus": "",
                "sign": "consume",
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
        return {
            "component": {
                "id": "",
                "bus": "",
                "vecteur": "diesel",
            }
        }
    return {"component": {"id": ""}}


def _modal_open_style() -> dict[str, str | int]:
    return {
        "display": "block",
        "position": "fixed",
        "inset": 0,
        "backgroundColor": "rgba(0,0,0,0.35)",
        "zIndex": 1000,
    }


def _modal_closed_style() -> dict[str, str]:
    return {"display": "none"}


def _config_dropdown_options() -> list[dict[str, str | int]]:
    return [{"label": r.name, "value": r.id} for r in list_vessel_configs()]


def _component_dropdown_options() -> list[dict[str, str | int]]:
    rows = list_component_templates()
    return [{"label": f"{r.component_type} | {r.name}", "value": r.id} for r in rows]


def _config_table_rows() -> list[html.Tr]:
    rows = list_vessel_configs()
    if not rows:
        return [html.Tr([html.Td("Aucune configuration en base.")])]
    return [html.Tr([html.Td(r.name), html.Td(r.updated_at)]) for r in rows]


def _component_table_rows() -> list[html.Tr]:
    rows = list_component_templates()
    if not rows:
        return [html.Tr([html.Td("Aucun template composant en base.")])]
    return [
        html.Tr([html.Td(r.component_type), html.Td(r.kind), html.Td(r.name), html.Td(r.updated_at)])
        for r in rows
    ]


layout = html.Div(
    [
        html.H3("Bibliotheque"),
        html.P("Gestion des configurations completes et des templates composants."),
        dcc.Interval(id="lib-onload-refresh", interval=200, n_intervals=0, max_intervals=1),
        dcc.Store(id="lib-selected-name"),
        dcc.Store(id="lib-pending-save"),
        dcc.Store(id="lib-component-selected-name"),
        dcc.Store(id="lib-comp-pending-save"),
        html.Div(
            [
                html.H4("Configurations completes"),
                dcc.Textarea(
                    id="lib-yaml",
                    value=load_default_yaml(),
                    style={"width": "100%", "height": "280px", "fontFamily": "Consolas, monospace"},
                ),
                html.Div(
                    [
                        html.Button("Sauver configuration", id="lib-save", n_clicks=0),
                        html.Button("Charger selection", id="lib-load", n_clicks=0, style={"marginLeft": "8px"}),
                        html.Button("Supprimer selection", id="lib-delete", n_clicks=0, style={"marginLeft": "8px"}),
                        html.Button("Rafraichir", id="lib-refresh", n_clicks=0, style={"marginLeft": "8px"}),
                    ],
                    style={"marginTop": "8px"},
                ),
                html.Div(id="lib-status", style={"marginTop": "10px"}),
                html.Label("Selection configuration"),
                dcc.Dropdown(
                    id="lib-select",
                    options=_config_dropdown_options(),
                    placeholder="Choisir une configuration",
                ),
                html.Table(
                    [
                        html.Thead(html.Tr([html.Th("Nom"), html.Th("Modifie le")])),
                        html.Tbody(id="lib-table-body", children=_config_table_rows()),
                    ],
                    style={"width": "100%", "marginTop": "8px"},
                ),
            ],
            style={"border": "1px solid #ddd", "borderRadius": "8px", "padding": "12px"},
        ),
        html.Div(style={"height": "16px"}),
        html.Div(
            [
                html.H4("Templates composants"),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Label("Nom template"),
                                                dcc.Input(id="lib-comp-name", type="text", style={"width": "100%"}),
                                            ],
                                            style={"width": "35%"},
                                        ),
                                        html.Div(
                                            [
                                                html.Label("Type"),
                                                dcc.Dropdown(
                                                    id="lib-comp-type",
                                                    options=COMPONENT_TYPE_OPTIONS,
                                                    value="converter",
                                                    clearable=False,
                                                ),
                                            ],
                                            style={"width": "20%"},
                                        ),
                                    ],
                                    style={"display": "flex", "gap": "10px"},
                                ),
                                html.Div(style={"height": "8px"}),
                                html.Label("Payload JSON (params + valeurs par defaut du composant)"),
                                dcc.Textarea(
                                    id="lib-comp-payload",
                                    value=json.dumps(_default_payload_for_component_type("converter"), ensure_ascii=False, indent=2),
                                    style={"width": "100%", "height": "180px", "fontFamily": "Consolas, monospace"},
                                ),
                                html.Div(
                                    [
                                        html.Button("Sauver template", id="lib-comp-save", n_clicks=0),
                                        html.Button("Charger selection", id="lib-comp-load", n_clicks=0, style={"marginLeft": "8px"}),
                                        html.Button("Supprimer selection", id="lib-comp-delete", n_clicks=0, style={"marginLeft": "8px"}),
                                        html.Button("Rafraichir", id="lib-comp-refresh", n_clicks=0, style={"marginLeft": "8px"}),
                                    ],
                                    style={"marginTop": "8px"},
                                ),
                                html.Div(id="lib-comp-status", style={"marginTop": "10px"}),
                                html.Label("Selection template"),
                                dcc.Dropdown(
                                    id="lib-comp-select",
                                    options=_component_dropdown_options(),
                                    placeholder="Choisir un template composant",
                                ),
                                html.Table(
                                    [
                                        html.Thead(
                                            html.Tr([html.Th("Type"), html.Th("Kind"), html.Th("Nom"), html.Th("Modifie le")])
                                        ),
                                        html.Tbody(id="lib-comp-table-body", children=_component_table_rows()),
                                    ],
                                    style={"width": "100%", "marginTop": "8px"},
                                ),
                            ],
                            style={"width": "52%"},
                        ),
                        html.Div(
                            [
                                html.H5("Guide YAML (lecture seule)"),
                                dcc.Markdown(
                                    _load_docs_markdown(),
                                    style={
                                        "maxHeight": "600px",
                                        "overflowY": "auto",
                                        "padding": "8px",
                                        "border": "1px solid #e5e7eb",
                                        "borderRadius": "6px",
                                        "backgroundColor": "#fafafa",
                                    },
                                ),
                            ],
                            style={"width": "46%"},
                        ),
                    ],
                    style={"display": "flex", "gap": "2%"},
                ),
            ],
            style={"border": "1px solid #ddd", "borderRadius": "8px", "padding": "12px"},
        ),
        html.Div(
            id="lib-save-modal",
            style=_modal_closed_style(),
            children=[
                html.Div(
                    [
                        html.H4("Sauvegarder la configuration"),
                        html.Label("Nom de configuration"),
                        dcc.Input(id="lib-save-name", type="text", style={"width": "100%"}),
                        html.Div(
                            [
                                html.Button("Confirmer", id="lib-confirm-save", n_clicks=0),
                                html.Button("Annuler", id="lib-cancel-save", n_clicks=0, style={"marginLeft": "8px"}),
                            ],
                            style={"marginTop": "12px"},
                        ),
                    ],
                    style={
                        "width": "420px",
                        "margin": "120px auto",
                        "background": "#fff",
                        "padding": "16px",
                        "borderRadius": "8px",
                        "boxShadow": "0 6px 20px rgba(0,0,0,0.2)",
                    },
                )
            ],
        ),
        html.Div(
            id="lib-overwrite-modal",
            style=_modal_closed_style(),
            children=[
                html.Div(
                    [
                        html.H4("Confirmer la mise a jour"),
                        html.Div(id="lib-overwrite-target"),
                        html.Div(
                            [
                                html.Button("Oui, mettre a jour", id="lib-confirm-overwrite", n_clicks=0),
                                html.Button("Annuler", id="lib-cancel-overwrite", n_clicks=0, style={"marginLeft": "8px"}),
                            ],
                            style={"marginTop": "12px"},
                        ),
                    ],
                    style={
                        "width": "420px",
                        "margin": "140px auto",
                        "background": "#fff",
                        "padding": "16px",
                        "borderRadius": "8px",
                        "boxShadow": "0 6px 20px rgba(0,0,0,0.2)",
                    },
                )
            ],
        ),
        html.Div(
            id="lib-comp-overwrite-modal",
            style=_modal_closed_style(),
            children=[
                html.Div(
                    [
                        html.H4("Confirmer la mise a jour du template"),
                        html.Div(id="lib-comp-overwrite-target"),
                        html.Div(
                            [
                                html.Button("Oui, mettre a jour", id="lib-comp-confirm-overwrite", n_clicks=0),
                                html.Button(
                                    "Annuler",
                                    id="lib-comp-cancel-overwrite",
                                    n_clicks=0,
                                    style={"marginLeft": "8px"},
                                ),
                            ],
                            style={"marginTop": "12px"},
                        ),
                    ],
                    style={
                        "width": "420px",
                        "margin": "160px auto",
                        "background": "#fff",
                        "padding": "16px",
                        "borderRadius": "8px",
                        "boxShadow": "0 6px 20px rgba(0,0,0,0.2)",
                    },
                )
            ],
        ),
        html.Div(style={"height": "120px"}),
    ]
)


@callback(
    Output("lib-select", "options"),
    Output("lib-table-body", "children"),
    Output("lib-comp-select", "options"),
    Output("lib-comp-table-body", "children"),
    Input("lib-onload-refresh", "n_intervals"),
    Input("lib-refresh", "n_clicks"),
    Input("lib-comp-refresh", "n_clicks"),
)
def refresh_list(_: int, __: int, ___: int):
    return _config_dropdown_options(), _config_table_rows(), _component_dropdown_options(), _component_table_rows()


@callback(
    Output("lib-selected-name", "data"),
    Output("lib-yaml", "value"),
    Output("lib-status", "children"),
    Input("lib-load", "n_clicks"),
    State("lib-select", "value"),
    prevent_initial_call=True,
)
def load_config(_: int, selected_id: int | None):
    if selected_id is None:
        return None, load_default_yaml(), "Selection vide."
    row = get_vessel_config(int(selected_id))
    if row is None:
        return None, load_default_yaml(), "Configuration introuvable."
    return row.name, row.yaml_text, f"Configuration chargee: {row.name}"


@callback(
    Output("lib-save-modal", "style"),
    Output("lib-save-name", "value"),
    Input("lib-save", "n_clicks"),
    Input("lib-cancel-save", "n_clicks"),
    State("lib-selected-name", "data"),
    prevent_initial_call=True,
)
def toggle_save_modal(open_clicks: int, cancel_clicks: int, selected_name: str | None):
    if open_clicks <= 0 and cancel_clicks <= 0:
        raise PreventUpdate
    if cancel_clicks >= open_clicks and cancel_clicks > 0:
        return _modal_closed_style(), selected_name or ""
    return _modal_open_style(), selected_name or ""


@callback(
    Output("lib-status", "children", allow_duplicate=True),
    Output("lib-select", "value"),
    Output("lib-select", "options", allow_duplicate=True),
    Output("lib-table-body", "children", allow_duplicate=True),
    Output("lib-save-modal", "style", allow_duplicate=True),
    Output("lib-selected-name", "data", allow_duplicate=True),
    Output("lib-overwrite-modal", "style"),
    Output("lib-overwrite-target", "children"),
    Output("lib-pending-save", "data"),
    Input("lib-confirm-save", "n_clicks"),
    State("lib-save-name", "value"),
    State("lib-yaml", "value"),
    prevent_initial_call=True,
)
def save_config(confirm_clicks: int, name: str | None, yaml_text: str | None):
    if confirm_clicks <= 0:
        raise PreventUpdate
    try:
        raw_name = (name or "").strip()
        raw_yaml = yaml_text or ""
        existing = get_vessel_config_by_name(raw_name)
        if existing is not None:
            return (
                "Configuration existante detectee. Confirmation requise.",
                no_update,
                _config_dropdown_options(),
                _config_table_rows(),
                _modal_closed_style(),
                no_update,
                _modal_open_style(),
                f'Le nom "{existing.name}" existe deja. Voulez-vous ecraser cette configuration ?',
                {"name": raw_name, "yaml_text": raw_yaml},
            )
        config_id = upsert_vessel_config(raw_name, raw_yaml)
        row = get_vessel_config(config_id)
        selected_name = row.name if row is not None else raw_name
        return (
            "Sauvegarde OK.",
            config_id,
            _config_dropdown_options(),
            _config_table_rows(),
            _modal_closed_style(),
            selected_name,
            _modal_closed_style(),
            "",
            None,
        )
    except Exception as exc:  # noqa: BLE001
        return (
            f"Erreur sauvegarde: {exc}",
            None,
            _config_dropdown_options(),
            _config_table_rows(),
            _modal_closed_style(),
            None,
            _modal_closed_style(),
            "",
            None,
        )


@callback(
    Output("lib-status", "children", allow_duplicate=True),
    Output("lib-select", "value", allow_duplicate=True),
    Output("lib-select", "options", allow_duplicate=True),
    Output("lib-table-body", "children", allow_duplicate=True),
    Output("lib-overwrite-modal", "style", allow_duplicate=True),
    Output("lib-overwrite-target", "children", allow_duplicate=True),
    Output("lib-pending-save", "data", allow_duplicate=True),
    Output("lib-selected-name", "data", allow_duplicate=True),
    Input("lib-confirm-overwrite", "n_clicks"),
    Input("lib-cancel-overwrite", "n_clicks"),
    State("lib-pending-save", "data"),
    prevent_initial_call=True,
)
def confirm_overwrite(confirm_clicks: int, cancel_clicks: int, pending: dict | None):
    triggered = ctx.triggered_id
    if triggered is None:
        raise PreventUpdate
    if triggered == "lib-cancel-overwrite":
        return (
            "Mise a jour annulee.",
            no_update,
            _config_dropdown_options(),
            _config_table_rows(),
            _modal_closed_style(),
            "",
            None,
            no_update,
        )
    if confirm_clicks <= 0 or not pending:
        raise PreventUpdate
    try:
        name = str(pending.get("name", "")).strip()
        yaml_text = str(pending.get("yaml_text", ""))
        config_id = upsert_vessel_config(name, yaml_text)
        row = get_vessel_config(config_id)
        selected_name = row.name if row is not None else name
        return (
            "Mise a jour effectuee.",
            config_id,
            _config_dropdown_options(),
            _config_table_rows(),
            _modal_closed_style(),
            "",
            None,
            selected_name,
        )
    except Exception as exc:  # noqa: BLE001
        return (
            f"Erreur update: {exc}",
            no_update,
            _config_dropdown_options(),
            _config_table_rows(),
            _modal_closed_style(),
            "",
            None,
            no_update,
        )


@callback(
    Output("lib-status", "children", allow_duplicate=True),
    Output("lib-selected-name", "data", allow_duplicate=True),
    Output("lib-select", "value", allow_duplicate=True),
    Output("lib-select", "options", allow_duplicate=True),
    Output("lib-table-body", "children", allow_duplicate=True),
    Input("lib-delete", "n_clicks"),
    State("lib-select", "value"),
    prevent_initial_call=True,
)
def remove_config(_: int, selected_id: int | None):
    if selected_id is None:
        return "Aucune configuration selectionnee.", None, None, _config_dropdown_options(), _config_table_rows()
    delete_vessel_config(int(selected_id))
    return "Suppression OK.", None, None, _config_dropdown_options(), _config_table_rows()


@callback(
    Output("lib-component-selected-name", "data"),
    Output("lib-comp-name", "value"),
    Output("lib-comp-type", "value"),
    Output("lib-comp-payload", "value"),
    Output("lib-comp-status", "children"),
    Input("lib-comp-load", "n_clicks"),
    State("lib-comp-select", "value"),
    prevent_initial_call=True,
)
def load_component(_: int, selected_id: int | None):
    if selected_id is None:
        default_payload = json.dumps(_default_payload_for_component_type("converter"), ensure_ascii=False, indent=2)
        return None, None, "converter", default_payload, "Selection vide."
    row = get_component_template(int(selected_id))
    if row is None:
        default_payload = json.dumps(_default_payload_for_component_type("converter"), ensure_ascii=False, indent=2)
        return None, None, "converter", default_payload, "Template introuvable."
    payload_text = json.dumps(row.payload, ensure_ascii=False, indent=2)
    return row.name, row.name, row.component_type, payload_text, f"Template charge: {row.name}"


@callback(
    Output("lib-comp-payload", "value", allow_duplicate=True),
    Input("lib-comp-type", "value"),
    State("lib-comp-select", "value"),
    prevent_initial_call=True,
)
def set_default_payload_by_type(component_type: str, selected_template_id: int | None):
    # En mode edition (template selectionne), ne pas ecraser le payload charge.
    if selected_template_id is not None:
        return no_update
    payload = _default_payload_for_component_type(component_type or "converter")
    return json.dumps(payload, ensure_ascii=False, indent=2)


@callback(
    Output("lib-comp-status", "children", allow_duplicate=True),
    Output("lib-comp-select", "value"),
    Output("lib-comp-select", "options", allow_duplicate=True),
    Output("lib-comp-table-body", "children", allow_duplicate=True),
    Output("lib-component-selected-name", "data", allow_duplicate=True),
    Output("lib-comp-overwrite-modal", "style"),
    Output("lib-comp-overwrite-target", "children"),
    Output("lib-comp-pending-save", "data"),
    Input("lib-comp-save", "n_clicks"),
    State("lib-comp-name", "value"),
    State("lib-comp-type", "value"),
    State("lib-comp-payload", "value"),
    prevent_initial_call=True,
)
def save_component(_: int, name: str | None, ctype: str | None, payload_text: str | None):
    try:
        raw_name = (name or "").strip()
        raw_type = (ctype or "").strip()
        raw_payload = payload_text or "{}"
        payload = json.loads(raw_payload)
        if not isinstance(payload, dict):
            raise ValueError("Le payload JSON doit etre un objet.")
        existing = get_component_template_by_name(raw_name)
        if existing is not None:
            effective_type = raw_type or existing.component_type
            return (
                "Template existant detecte. Confirmation requise.",
                no_update,
                _component_dropdown_options(),
                _component_table_rows(),
                no_update,
                _modal_open_style(),
                f'Le template "{existing.name}" existe deja. Voulez-vous vraiment le mettre a jour ?',
                {"name": raw_name, "component_type": effective_type, "payload": payload},
            )

        template_id = upsert_component_template(raw_name, raw_type, payload)
        return (
            "Creation template OK.",
            template_id,
            _component_dropdown_options(),
            _component_table_rows(),
            raw_name,
            _modal_closed_style(),
            "",
            None,
        )
    except Exception as exc:  # noqa: BLE001
        return (
            f"Erreur template: {exc}",
            None,
            _component_dropdown_options(),
            _component_table_rows(),
            no_update,
            _modal_closed_style(),
            "",
            None,
        )


@callback(
    Output("lib-comp-status", "children", allow_duplicate=True),
    Output("lib-comp-select", "value", allow_duplicate=True),
    Output("lib-comp-select", "options", allow_duplicate=True),
    Output("lib-comp-table-body", "children", allow_duplicate=True),
    Output("lib-component-selected-name", "data", allow_duplicate=True),
    Output("lib-comp-overwrite-modal", "style", allow_duplicate=True),
    Output("lib-comp-overwrite-target", "children", allow_duplicate=True),
    Output("lib-comp-pending-save", "data", allow_duplicate=True),
    Input("lib-comp-confirm-overwrite", "n_clicks"),
    Input("lib-comp-cancel-overwrite", "n_clicks"),
    State("lib-comp-pending-save", "data"),
    prevent_initial_call=True,
)
def confirm_component_overwrite(confirm_clicks: int, cancel_clicks: int, pending: dict | None):
    triggered = ctx.triggered_id
    if triggered is None:
        raise PreventUpdate

    if triggered == "lib-comp-cancel-overwrite":
        return (
            "Mise a jour template annulee.",
            no_update,
            _component_dropdown_options(),
            _component_table_rows(),
            no_update,
            _modal_closed_style(),
            "",
            None,
        )

    if confirm_clicks <= 0 or not pending:
        raise PreventUpdate
    try:
        name = str(pending.get("name", "")).strip()
        ctype = str(pending.get("component_type", "")).strip()
        payload = pending.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError("Payload en attente invalide.")
        if not ctype:
            existing = get_component_template_by_name(name)
            if existing is None:
                raise ValueError("Template cible introuvable pour determiner le type.")
            ctype = existing.component_type
        template_id = upsert_component_template(name, ctype, payload)
        return (
            "Mise a jour template OK.",
            template_id,
            _component_dropdown_options(),
            _component_table_rows(),
            name,
            _modal_closed_style(),
            "",
            None,
        )
    except Exception as exc:  # noqa: BLE001
        return (
            f"Erreur update template: {exc}",
            no_update,
            _component_dropdown_options(),
            _component_table_rows(),
            no_update,
            _modal_closed_style(),
            "",
            None,
        )


@callback(
    Output("lib-comp-status", "children", allow_duplicate=True),
    Output("lib-component-selected-name", "data", allow_duplicate=True),
    Output("lib-comp-select", "value", allow_duplicate=True),
    Output("lib-comp-select", "options", allow_duplicate=True),
    Output("lib-comp-table-body", "children", allow_duplicate=True),
    Input("lib-comp-delete", "n_clicks"),
    State("lib-comp-select", "value"),
    prevent_initial_call=True,
)
def remove_component(_: int, selected_id: int | None):
    if selected_id is None:
        return (
            "Aucun template selectionne.",
            no_update,
            None,
            _component_dropdown_options(),
            _component_table_rows(),
        )
    delete_component_template(int(selected_id))
    return "Suppression template OK.", None, None, _component_dropdown_options(), _component_table_rows()
