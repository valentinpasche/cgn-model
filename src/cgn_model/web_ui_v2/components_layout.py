"""Layout UI V2 composants."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html
from dash_extensions import Mermaid

from cgn_model.web_ui_v2.components_registry import (
    TYPE_OPTIONS,
    model_options,
    render_form,
    render_schema_form,
)


def build_layout():
    default_key = "profile.nav_speed"
    return dmc.MantineProvider(
        html.Div(
            [
                html.H1("CGN - Interface bateau, simulation énergétique"),
                dcc.Interval(id="v2m-refresh", interval=300, n_intervals=0, max_intervals=1),
                dcc.Store(id="v2db-rev", data=0),
                dcc.Store(id="v2m-form-seed", data={}),
                dcc.Store(id="v2m-reset-guard", data=False),
                dcc.Store(id="v2m-pending-save", data={}),
                dcc.Store(id="v2s-pending-save", data={}),
                dcc.Store(id="v2s-current", data={"name": "", "components": []}),
                dcc.Store(id="v2c-json-store", data={}),
                dcc.Store(id="v2c-yaml-store", data={}),
                dcc.Store(id="v2sim-last-run", data={}),
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
                    id="v2s-update-modal",
                    title="Confirmation mise a jour",
                    opened=False,
                    children=[
                        html.P("Ce nom de schema existe deja. Voulez-vous le mettre a jour ?"),
                        html.Div(
                            [
                                html.Button("Oui, mettre a jour", id="v2s-update-yes", n_clicks=0),
                                html.Button("Annuler", id="v2s-update-no", n_clicks=0, style={"marginLeft": "8px"}),
                            ],
                            style={"marginTop": "8px"},
                        ),
                    ],
                ),
                dmc.Modal(
                    id="v2s-delete-modal",
                    title="Confirmation suppression",
                    opened=False,
                    children=[
                        html.P("Voulez-vous vraiment supprimer ce schema ?"),
                        html.Div(
                            [
                                html.Button("Oui, supprimer", id="v2s-delete-yes", n_clicks=0),
                                html.Button("Annuler", id="v2s-delete-no", n_clicks=0, style={"marginLeft": "8px"}),
                            ],
                            style={"marginTop": "8px"},
                        ),
                    ],
                ),
                dmc.Modal(
                    id="v2c-json-modal",
                    title="JSON schema valide",
                    opened=False,
                    size="xl",
                    children=[
                        html.Pre(id="v2c-json-content", style={"whiteSpace": "pre-wrap", "fontSize": "0.88rem"}),
                        html.Div(
                            [html.Button("Fermer", id="v2c-json-close", n_clicks=0)],
                            style={"marginTop": "10px"},
                        ),
                    ],
                ),
                dmc.Modal(
                    id="v2c-yaml-modal",
                    title="YAML compilé",
                    opened=False,
                    size="xl",
                    children=[
                        html.Pre(id="v2c-yaml-content", style={"whiteSpace": "pre-wrap", "fontSize": "0.88rem"}),
                        html.Div(
                            [html.Button("Fermer", id="v2c-yaml-close", n_clicks=0)],
                            style={"marginTop": "10px"},
                        ),
                    ],
                ),
                html.Div(
                    [
                        # Haut gauche: schemas
                        html.Div(
                            [
                                html.H3("Gestion des schémas (DB)", style={"fontSize": "1.35rem", "marginBottom": "6px"}),
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                dcc.Dropdown(id="v2s-select", options=[], placeholder="Selectionner un schema en base", style={"flex": "1 1 auto", "minWidth": "220px"}),
                                            ],
                                            style={"display": "flex", "alignItems": "center", "marginBottom": "8px", "width": "100%"},
                                        ),
                                        html.Div(
                                            [
                                                html.Button("Charger, Editer le schema", id="v2s-load", n_clicks=0),
                                                html.Button("Reinitialiser", id="v2s-refresh", n_clicks=0, style={"marginLeft": "8px"}),
                                                html.Button("Supprimer", id="v2s-delete", n_clicks=0, style={"marginLeft": "8px"}),
                                            ],
                                            style={"marginBottom": "8px"},
                                        ),
                                        html.Div(id="v2s-form-container", children=render_schema_form({"name": "", "components": []})),
                                        html.Div(
                                            [
                                                html.Button("Valider", id="v2s-validate", n_clicks=0),
                                                html.Button("Sauvegarder", id="v2s-save", n_clicks=0, style={"marginLeft": "8px"}),
                                            ],
                                            style={"marginTop": "10px"},
                                        ),
                                        html.Div(id="v2s-status", style={"marginTop": "8px"}),
                                    ],
                                    style={"width": "100%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px", "height": "100%"},
                                ),
                            ],
                            style={"gridColumn": "1", "gridRow": "1", "display": "flex"},
                        ),
                        # Haut droite: visualisation + compilation
                        html.Div(
                            [
                                html.H3("Visualisation - Compilation - Simulation", style={"fontSize": "1.35rem", "marginBottom": "6px"}),
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Button("JSON", id="v2c-show-json", n_clicks=0),
                                                html.Button("Compiler", id="v2c-compile", n_clicks=0, style={"marginLeft": "8px"}),
                                                html.Button("YAML", id="v2c-show-yaml", n_clicks=0, style={"marginLeft": "8px"}),
                                                html.Button("Simuler", id="v2c-simulate", n_clicks=0, style={"marginLeft": "8px"}),
                                            ],
                                            style={"marginBottom": "8px"},
                                        ),
                                        html.Div(id="v2c-status", style={"marginBottom": "8px"}),
                                        html.Div(
                                            dcc.RadioItems(
                                                id="v2cfg-view-mode",
                                                options=[
                                                    {"label": "Schéma en cours", "value": "simple"},
                                                    {"label": "Configuration compilée", "value": "yaml"},
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
                                            id="v2cfg-mermaid-container",
                                            style={"minHeight": "360px"},
                                        ),
                                    ],
                                    style={"border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px", "height": "100%"},
                                ),
                            ],
                            style={"gridColumn": "2", "gridRow": "1", "display": "flex"},
                        ),
                        # Bas gauche: composants
                        html.Div(
                            [
                                html.H3("Gestion des composants (DB)", style={"fontSize": "1.35rem", "marginBottom": "6px"}),
                                html.Div(
                                    [
                                        dcc.Dropdown(id="v2m-select", options=[], placeholder="Selectionner un composant en base", style={"width": "100%"}),
                                        html.Div(
                                            [
                                                html.Button("Charger, Editer le formulaire", id="v2m-load-edit", n_clicks=0),
                                                html.Button("Reinitialiser", id="v2db-refresh", n_clicks=0, style={"marginLeft": "8px"}),
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
                                        html.Div(id="v2m-status", style={"marginTop": "8px"}),
                                    ],
                                    style={"width": "100%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px"},
                                ),
                            ],
                            style={"gridColumn": "1", "gridRow": "2"},
                        ),
                        # Bas droite: resultats placeholder
                        html.Div(
                            [
                                html.H3("Resultats", style={"fontSize": "1.35rem", "marginBottom": "6px"}),
                                html.Div(
                                    [
                                        html.P("Zone placeholder (graphique + export)."),
                                        html.Div(id="v2r-sim-summary", style={"marginTop": "8px"}),
                                    ],
                                    style={
                                        "border": "1px solid #ddd",
                                        "borderRadius": "8px",
                                        "padding": "10px",
                                        "minHeight": "360px",
                                        "backgroundColor": "#fafafa",
                                    },
                                ),
                            ],
                            style={"gridColumn": "2", "gridRow": "2"},
                        ),
                    ],
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "1fr 1fr",
                        "gridTemplateRows": "auto auto",
                        "gap": "12px",
                        "alignItems": "stretch",
                    },
                ),
            ],
            style={"margin": "16px"},
        )
    )
