"""Layout UI V2 composants."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dash_table, dcc, html
from dash_extensions import Mermaid

from components_registry import TYPE_OPTIONS, default_model_key, model_options, render_form


def build_layout():
    default_key = default_model_key("converter")
    return dmc.MantineProvider(
        html.Div(
            [
                html.H2("CGN - Interface bateau (V2)"),
                dcc.Interval(id="v2m-refresh", interval=300, n_intervals=0, max_intervals=1),
                dcc.Store(id="v2m-local-components", data=[]),
                dcc.Store(id="v2m-form-seed", data={}),
                dcc.Store(id="v2m-pending-save", data={}),
                dcc.Store(id="v2cfg-local-configs", data=[]),
                dcc.Store(id="v2cfg-current", data={"name": "config_local", "components": []}),
                dcc.Store(id="v2cfg-pending-load", data={}),
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
                dmc.Modal(
                    id="v2cfg-conflict-modal",
                    title="Conflits de noms composants",
                    opened=False,
                    children=[
                        html.P("Des composants de meme nom existent deja en local. Voulez-vous les ecraser ?"),
                        html.Div(
                            [
                                html.Button("Oui, ecraser", id="v2cfg-conflict-yes", n_clicks=0),
                                html.Button("Annuler", id="v2cfg-conflict-no", n_clicks=0, style={"marginLeft": "8px"}),
                            ],
                            style={"marginTop": "8px"},
                        ),
                    ],
                ),
                html.H3("Configuration complete", style={"fontSize": "1.45rem", "marginBottom": "6px"}),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        dcc.Dropdown(
                                            id="v2cfg-select",
                                            options=[],
                                            placeholder="Charger une configuration (local/DB)",
                                            style={"flex": "1 1 auto", "minWidth": "260px"},
                                        ),
                                        html.Div(
                                            [
                                                html.Button("Charger", id="v2cfg-load", n_clicks=0),
                                                html.Button("Sauvegarder", id="v2cfg-save", n_clicks=0, style={"marginLeft": "8px"}),
                                                html.Button("Valider", id="v2cfg-validate", n_clicks=0, style={"marginLeft": "8px"}),
                                            ],
                                            style={"display": "flex", "alignItems": "center", "flex": "0 0 auto", "marginLeft": "8px"},
                                        ),
                                    ],
                                    style={"display": "flex", "alignItems": "center", "marginBottom": "8px", "width": "100%"},
                                ),
                                html.Div(
                                    id="v2cfg-save-choice",
                                    style={"display": "none", "marginBottom": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"},
                                    children=[
                                        html.Div(
                                            [
                                                dcc.Input(id="v2cfg-save-name", type="text", value="config_local", style={"flex": "1 1 auto", "minWidth": "180px"}),
                                                html.Button("Sauvegarder local", id="v2cfg-save-local", n_clicks=0, style={"marginLeft": "8px"}),
                                                html.Button("Sauvegarder DB", id="v2cfg-save-db", n_clicks=0, style={"marginLeft": "8px"}),
                                                html.Button("Annuler", id="v2cfg-save-cancel", n_clicks=0, style={"marginLeft": "8px"}),
                                            ],
                                            style={"display": "flex", "alignItems": "center", "width": "100%"},
                                        )
                                    ],
                                ),
                                html.Div(
                                    [
                                        dcc.Dropdown(
                                            id="v2cfg-add-component",
                                            options=[],
                                            placeholder="Ajouter un composant local",
                                            style={"flex": "1 1 auto", "minWidth": "220px"},
                                        ),
                                        html.Button("Ajouter", id="v2cfg-add-btn", n_clicks=0, style={"marginLeft": "8px", "flex": "0 0 130px"}),
                                    ],
                                    style={"display": "flex", "alignItems": "center", "marginBottom": "8px", "width": "100%"},
                                ),
                                html.Div(
                                    [
                                        dcc.Dropdown(
                                            id="v2cfg-remove-component",
                                            options=[],
                                            placeholder="Supprimer un composant",
                                            style={"flex": "1 1 auto", "minWidth": "220px"},
                                        ),
                                        html.Button("Supprimer", id="v2cfg-remove-btn", n_clicks=0, style={"marginLeft": "8px", "flex": "0 0 130px"}),
                                    ],
                                    style={"display": "flex", "alignItems": "center", "marginBottom": "8px", "width": "100%"},
                                ),
                            ],
                            style={"width": "49%", "border": "1px solid #e5e5e5", "borderRadius": "8px", "padding": "10px", "display": "flex", "flexDirection": "column"},
                        ),
                        html.Div(
                            [
                                html.Div(id="v2cfg-status", style={"marginBottom": "8px"}),
                                Mermaid(id="v2cfg-mermaid", chart="flowchart LR\n  n0[Configuration vide]"),
                                html.Div(style={"height": "8px"}),
                                dash_table.DataTable(
                                    id="v2cfg-table",
                                    columns=[
                                        {"name": "Nom config", "id": "name"},
                                        {"name": "Nb composants", "id": "n_components"},
                                        {"name": "Statut", "id": "status"},
                                    ],
                                    data=[],
                                    page_size=6,
                                    style_table={"overflowX": "auto"},
                                ),
                            ],
                            style={"width": "49%", "border": "1px solid #e5e5e5", "borderRadius": "8px", "padding": "10px"},
                        ),
                    ],
                    style={"display": "flex", "gap": "2%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px", "marginBottom": "10px"},
                ),
                html.H3("Gestion des composants uniquement (local + DB)", style={"fontSize": "1.35rem", "marginBottom": "6px"}),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Label("Type composant"),
                                dcc.Dropdown(id="v2m-type", options=TYPE_OPTIONS, value="converter", clearable=False),
                                html.Div(style={"height": "8px"}),
                                html.Label("Modele composant"),
                                dcc.Dropdown(id="v2m-model", options=model_options("converter"), value=default_key, clearable=False),
                                html.Div(style={"height": "10px"}),
                                html.Div(id="v2m-form-container", children=render_form(default_key, {})),
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
                                dcc.Dropdown(id="v2m-select", options=[], placeholder="Selectionner un composant", style={"width": "100%"}),
                                html.Div(
                                    [
                                        html.Button("Charger, Editer le formulaire", id="v2m-load-edit", n_clicks=0),
                                        html.Button("Supprimer", id="v2m-delete", n_clicks=0, style={"marginLeft": "8px"}),
                                    ],
                                    style={"marginTop": "8px", "marginBottom": "8px"},
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
                                    page_size=12,
                                    style_table={"overflowX": "auto"},
                                ),
                            ],
                            style={"width": "49%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px"},
                        ),
                    ],
                    style={"display": "flex", "gap": "2%"},
                ),
            ],
            style={"margin": "16px"},
        )
    )
