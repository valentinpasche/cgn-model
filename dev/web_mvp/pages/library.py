"""
Page CRUD minimale pour les configurations vessel (SQLite).
"""

from __future__ import annotations

from dash import Input, Output, State, callback, ctx, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate

from services.db import (
    delete_vessel_config,
    get_vessel_config,
    get_vessel_config_by_name,
    list_vessel_configs,
    upsert_vessel_config,
)
from services.default_yaml import load_default_yaml

register_page(__name__, path="/library", name="Bibliotheque")


def _dropdown_options() -> list[dict[str, str | int]]:
    rows = list_vessel_configs()
    return [{"label": r.name, "value": r.id} for r in rows]


def _table_rows() -> list[html.Tr]:
    rows = list_vessel_configs()
    if not rows:
        return [html.Tr([html.Td("Aucune configuration en base.")])]
    return [html.Tr([html.Td(r.name), html.Td(r.updated_at)]) for r in rows]


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


layout = html.Div(
    [
        html.H3("Bibliotheque de configurations"),
        html.P("CRUD minimal SQLite: creer, charger, supprimer une config YAML."),
        dcc.Interval(id="lib-onload-refresh", interval=200, n_intervals=0, max_intervals=1),
        dcc.Store(id="lib-selected-name"),
        dcc.Store(id="lib-pending-save"),
        dcc.Textarea(
            id="lib-yaml",
            value=load_default_yaml(),
            style={"width": "100%", "height": "320px", "fontFamily": "Consolas, monospace"},
        ),
        html.Br(),
        html.Button("Sauver (create/update)", id="lib-save", n_clicks=0),
        html.Button("Charger selection", id="lib-load", n_clicks=0, style={"marginLeft": "8px"}),
        html.Button("Supprimer selection", id="lib-delete", n_clicks=0, style={"marginLeft": "8px"}),
        html.Button("Rafraichir liste", id="lib-refresh", n_clicks=0, style={"marginLeft": "8px"}),
        html.Div(id="lib-status", style={"marginTop": "10px"}),
        html.H4("Selection"),
        dcc.Dropdown(id="lib-select", options=_dropdown_options(), placeholder="Choisir une configuration"),
        html.H4("Configurations en base"),
        html.Table(
            [
                html.Thead(html.Tr([html.Th("Nom"), html.Th("Modifie le")])),
                html.Tbody(id="lib-table-body", children=_table_rows()),
            ],
            style={"width": "100%", "marginTop": "8px"},
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
                                html.Button(
                                    "Annuler",
                                    id="lib-cancel-overwrite",
                                    n_clicks=0,
                                    style={"marginLeft": "8px"},
                                ),
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
    ]
)


@callback(
    Output("lib-select", "options"),
    Output("lib-table-body", "children"),
    Input("lib-onload-refresh", "n_intervals"),
    Input("lib-refresh", "n_clicks"),
)
def refresh_list(_: int, __: int):
    return _dropdown_options(), _table_rows()


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
                _dropdown_options(),
                _table_rows(),
                _modal_closed_style(),
                no_update,
                _modal_open_style(),
                f'Le nom "{existing.name}" existe deja. Voulez-vous vraiment ecraser cette configuration ?',
                {"name": raw_name, "yaml_text": raw_yaml},
            )

        config_id = upsert_vessel_config(raw_name, raw_yaml)
        row = get_vessel_config(config_id)
        selected_name = row.name if row is not None else (name or "")
        return (
            "Sauvegarde OK.",
            config_id,
            _dropdown_options(),
            _table_rows(),
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
            _dropdown_options(),
            _table_rows(),
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
            _dropdown_options(),
            _table_rows(),
            _modal_closed_style(),
            "",
            None,
            no_update,
        )

    if confirm_clicks <= 0:
        raise PreventUpdate
    if not pending:
        return (
            "Aucune sauvegarde en attente.",
            no_update,
            _dropdown_options(),
            _table_rows(),
            _modal_closed_style(),
            "",
            None,
            no_update,
        )

    try:
        name = str(pending.get("name", "")).strip()
        yaml_text = str(pending.get("yaml_text", ""))
        config_id = upsert_vessel_config(name, yaml_text)
        row = get_vessel_config(config_id)
        selected_name = row.name if row is not None else name
        return (
            "Mise a jour effectuee.",
            config_id,
            _dropdown_options(),
            _table_rows(),
            _modal_closed_style(),
            "",
            None,
            selected_name,
        )
    except Exception as exc:  # noqa: BLE001
        return (
            f"Erreur update: {exc}",
            no_update,
            _dropdown_options(),
            _table_rows(),
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
        return "Aucune configuration selectionnee.", None, None, _dropdown_options(), _table_rows()
    delete_vessel_config(int(selected_id))
    return "Suppression OK.", None, None, _dropdown_options(), _table_rows()
