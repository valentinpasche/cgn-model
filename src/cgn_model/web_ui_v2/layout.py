"""Layout interface web V2."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html
from dash_extensions import Mermaid

from cgn_model.web_ui_v2.registry import (
    TYPE_OPTIONS,
    model_options,
    render_form,
    render_schema_form,
)


def _credits_footer():
    return html.Div(
        [
            html.Img(
                src="/assets/CGN_logo.svg",
                alt="CGN logo",
                style={"height": "34px", "width": "auto"},
            ),
            html.P(
                "Interface realisee pour `CGN Model`, basée sur `Dash pydantic form` - credits: V. Pasche (HEIA-FR) + R. Baur (CGN)",
                style={"margin": 0, "fontWeight": 600},
            ),
            html.Div(
                [
                    html.Img(
                        src="/assets/SeSi_logo.svg",
                        alt="SeSi logo",
                        style={"height": "34px", "width": "auto", "marginRight": "30px"},
                    ),
                    html.Img(
                        src="/assets/HEIA_FR_logo.svg",
                        alt="HEIA-FR logo",
                        style={"height": "34px", "width": "auto", "marginRight": "100px"},
                    ),
                ]
            ),
        ],
        style={
            "position": "fixed",
            "left": 0,
            "right": 0,
            "bottom": 0,
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "padding": "8px 16px",
            "fontSize": "0.9rem",
            "color": "#1f2937",
            "background": "#f8fafc",
            "borderTop": "1px solid #d1d5db",
            "zIndex": 1000,
        },
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
                dcc.Store(id="v2sim-df-store", data={}),
                dcc.Download(id="v2r-csv-download"),
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
                dmc.Modal(
                    id="v2r-plot-modal",
                    title="Résultats simulation - Graphique",
                    opened=False,
                    size="95%",
                    children=[
                        dcc.Graph(
                            id="v2r-graph-large",
                            figure={
                                "data": [],
                                "layout": {
                                    "title": "Résultats simulation - Preview",
                                    "template": "plotly_white",
                                    "height": 720,
                                },
                            },
                            config={"displaylogo": False, "responsive": True},
                            style={"height": "75vh"},
                        ),
                        html.Div(
                            [html.Button("Fermer", id="v2r-close-plot", n_clicks=0)],
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
                                    style={"width": "100%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px"},
                                ),
                            ],
                            style={"gridColumn": "1", "gridRow": "1"},
                        ),
                        # Haut droite: visualisation + compilation
                        html.Div(
                            [
                                html.H3("Visualisation - Compilation - Simulation", style={"fontSize": "1.35rem", "marginBottom": "6px"}),
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Button("Compiler", id="v2c-compile", n_clicks=0),
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
                                            className="cgn-mermaid-frame",
                                            style={"minHeight": "360px"},
                                        ),
                                    ],
                                    style={"border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px", "minHeight": "640px"},
                                ),
                            ],
                            style={"gridColumn": "2", "gridRow": "1"},
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
                                        html.Div(id="v2r-sim-summary", style={"marginTop": "8px"}),
                                        html.Hr(),
                                        html.Label("Colonnes a afficher / exporter"),
                                        dcc.Dropdown(
                                            id="v2r-cols",
                                            options=[],
                                            value=[],
                                            multi=True,
                                            placeholder="Selectionner les colonnes du resultat",
                                            style={"marginBottom": "8px"},
                                        ),
                                        html.Div(
                                            [
                                                html.Button("Exporter CSV", id="v2r-export-csv", n_clicks=0),
                                                html.Button("Ouvrire le graphique", id="v2r-open-plot", n_clicks=0, style={"marginLeft": "8px"}),
                                            ],
                                            style={"marginBottom": "8px"},
                                        ),
                                        dcc.Graph(
                                            id="v2r-graph",
                                            figure={
                                                "data": [],
                                                "layout": {
                                                    "title": "Aucun resultat de simulation",
                                                    "template": "plotly_white",
                                                    "height": 320,
                                                },
                                            },
                                            config={"displaylogo": False, "responsive": True},
                                            style={"height": "320px"},
                                        ),
                                    ],
                                    style={
                                        "border": "1px solid #ddd",
                                        "borderRadius": "8px",
                                        "padding": "10px",
                                        "minHeight": "460px",
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
                        "alignItems": "start",
                    },
                ),
                _credits_footer(),
            ],
            style={"margin": "16px", "paddingBottom": "64px"},
        )
    )
