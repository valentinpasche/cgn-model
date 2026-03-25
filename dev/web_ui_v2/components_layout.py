"""Layout UI V2 composants."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dash_table, dcc, html
from dash_extensions import Mermaid

from components_registry import TYPE_OPTIONS, model_options, render_form


def build_layout():
    default_key = "profile.nav_speed"
    return dmc.MantineProvider(
        html.Div(
            [
                html.H2("CGN - Interface bateau (V2)"),
                dcc.Interval(id="v2m-refresh", interval=300, n_intervals=0, max_intervals=1),
                dcc.Store(id="v2db-rev", data=0),
                dcc.Store(id="v2m-form-seed", data={}),
                dcc.Store(id="v2m-pending-save", data={}),
                dcc.Store(id="v2s-current", data={"name": "schema_local", "components": []}),
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
                html.H3("Schemas (DB)", style={"fontSize": "1.45rem", "marginBottom": "6px"}),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        dcc.Input(id="v2s-name", type="text", value="schema_local", style={"flex": "1 1 auto", "minWidth": "180px"}),
                                        dcc.Dropdown(id="v2s-select", options=[], placeholder="Schema en base", style={"flex": "1 1 auto", "minWidth": "220px", "marginLeft": "8px"}),
                                        html.Button("Charger", id="v2s-load", n_clicks=0, style={"marginLeft": "8px"}),
                                        html.Button("Sauvegarder", id="v2s-save", n_clicks=0, style={"marginLeft": "8px"}),
                                        html.Button("Supprimer", id="v2s-delete", n_clicks=0, style={"marginLeft": "8px"}),
                                        html.Button("Valider", id="v2s-validate", n_clicks=0, style={"marginLeft": "8px"}),
                                    ],
                                    style={"display": "flex", "alignItems": "center", "marginBottom": "8px", "width": "100%"},
                                ),
                                html.Div(
                                    [
                                        dcc.Dropdown(
                                            id="v2s-add-component",
                                            options=[],
                                            placeholder="Ajouter un composant (DB)",
                                            style={"flex": "1 1 auto", "minWidth": "220px"},
                                        ),
                                        html.Button("Ajouter", id="v2s-add-btn", n_clicks=0, style={"marginLeft": "8px", "flex": "0 0 130px"}),
                                    ],
                                    style={"display": "flex", "alignItems": "center", "marginBottom": "8px", "width": "100%"},
                                ),
                                html.Div(
                                    [
                                        dcc.Dropdown(
                                            id="v2s-remove-component",
                                            options=[],
                                            placeholder="Supprimer un composant du schema",
                                            style={"flex": "1 1 auto", "minWidth": "220px"},
                                        ),
                                        html.Button("Supprimer", id="v2s-remove-btn", n_clicks=0, style={"marginLeft": "8px", "flex": "0 0 130px"}),
                                    ],
                                    style={"display": "flex", "alignItems": "center", "marginBottom": "8px", "width": "100%"},
                                ),
                                html.Div(id="v2s-status"),
                            ],
                            style={"width": "49%", "border": "1px solid #e5e5e5", "borderRadius": "8px", "padding": "10px", "display": "flex", "flexDirection": "column"},
                        ),
                        html.Div(
                            [
                                dash_table.DataTable(
                                    id="v2s-table",
                                    columns=[
                                        {"name": "Composant", "id": "id"},
                                        {"name": "Statut", "id": "status"},
                                        {"name": "Modele", "id": "model"},
                                    ],
                                    data=[],
                                    page_size=8,
                                    style_table={"overflowX": "auto"},
                                ),
                            ],
                            style={"width": "49%", "border": "1px solid #e5e5e5", "borderRadius": "8px", "padding": "10px"},
                        ),
                    ],
                    style={"display": "flex", "gap": "2%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px", "marginBottom": "10px"},
                ),
                html.H3("Visualisation du schema", style={"fontSize": "1.35rem", "marginBottom": "6px"}),
                html.Div(
                    [
                        html.Div(
                            dcc.RadioItems(
                                id="v2cfg-view-mode",
                                options=[
                                    {"label": "Vue simple", "value": "simple", "disabled": True},
                                    {"label": "Vue detaillee", "value": "detailed", "disabled": True},
                                ],
                                value="simple",
                                inline=True,
                                inputStyle={"marginRight": "6px", "marginLeft": "10px"},
                            ),
                            style={"marginBottom": "8px"},
                        ),
                        html.Div(
                            [
                                Mermaid(
                                    id="v2cfg-mermaid",
                                    chart='flowchart LR\n  n0["Visualisation schema en cours"]\n  n1["Placeholder"]\n  n0 --> n1',
                                )
                            ],
                            style={"minHeight": "360px"},
                        ),
                    ],
                    style={"border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px", "marginBottom": "10px"},
                ),
                html.H3("Gestion des composants (DB)", style={"fontSize": "1.35rem", "marginBottom": "6px"}),
                html.Div(
                    [
                        html.Div(
                            [
                                dcc.Dropdown(id="v2m-select", options=[], placeholder="Selectionner un composant en base", style={"width": "100%"}),
                                html.Div(
                                    [
                                        html.Button("Charger, Editer le formulaire", id="v2m-load-edit", n_clicks=0),
                                        html.Button("Rafraichir", id="v2db-refresh", n_clicks=0, style={"marginLeft": "8px"}),
                                        html.Button("Supprimer", id="v2m-delete", n_clicks=0, style={"marginLeft": "8px"}),
                                    ],
                                    style={"marginTop": "8px", "marginBottom": "8px"},
                                ),
                                html.Label("Type de composant"),
                                dcc.Dropdown(id="v2m-type", options=TYPE_OPTIONS, value="profile", clearable=False),
                                html.Div(style={"height": "8px"}),
                                html.Label("Modele de composant"),
                                dcc.Dropdown(id="v2m-model", options=model_options("profile"), value=default_key, clearable=False),
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
                                        html.Button("DB", id="v2m-save-db", n_clicks=0, style={"marginLeft": "8px"}),
                                        html.Button("Annuler", id="v2m-save-cancel", n_clicks=0, style={"marginLeft": "8px"}),
                                    ],
                                ),
                                html.Div(id="v2m-status", style={"marginTop": "8px"}),
                            ],
                            style={"width": "100%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px"},
                        ),
                    ],
                    style={"display": "flex"},
                ),
            ],
            style={"margin": "16px"},
        )
    )

