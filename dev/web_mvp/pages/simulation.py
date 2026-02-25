"""
Page d'execution simulation (YAML en lecture seule).
"""

from __future__ import annotations

import pandas as pd
import yaml
from dash import Input, Output, State, callback, dash_table, dcc, html, register_page
from dash_extensions import Mermaid
import plotly.express as px

from services.dag_mermaid import yaml_to_mermaid
from services.db import get_vessel_config, list_vessel_configs
from services.simulation import run_simulation_from_yaml

register_page(__name__, path="/simulation", name="Simulation")


def _sim_options() -> list[dict[str, str | int]]:
    rows = list_vessel_configs()
    return [{"label": r.name, "value": r.id} for r in rows]


def _build_plot(df: pd.DataFrame):
    time_col = "time_s" if "time_s" in df.columns else None
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if time_col and len(numeric_cols) > 1:
        y_col = next((c for c in numeric_cols if c != time_col), numeric_cols[0])
        return px.line(df, x=time_col, y=y_col, title=f"{y_col} en fonction du temps")
    if numeric_cols:
        return px.line(df, y=numeric_cols[0], title=numeric_cols[0])
    return px.scatter(title="Aucune serie numerique exploitable")


layout = html.Div(
    [
        html.H3("Simulation"),
        dcc.Interval(id="sim-onload-refresh", interval=200, n_intervals=0, max_intervals=1),
        dcc.Store(id="sim-yaml-store", data=""),
        dcc.Store(id="sim-mermaid-store", data="flowchart LR\n  a[no_data]"),
        html.Div(
            [
                html.Label("Configuration a simuler"),
                dcc.Dropdown(id="sim-select", options=_sim_options(), placeholder="Choisir une configuration"),
            ]
        ),
        html.Br(),
        html.Label("Vue configuration"),
        dcc.RadioItems(
            id="sim-view-mode",
            options=[
                {"label": "Texte", "value": "text"},
                {"label": "Mermaid", "value": "mermaid"},
            ],
            value="text",
            inline=True,
        ),
        html.Br(),
        html.Label("YAML / Mermaid (lecture seule)"),
        html.Div(id="sim-config-view"),
        html.Br(),
        html.Button("Lancer simulation", id="btn-run-sim", n_clicks=0),
        html.Div(id="sim-status", style={"marginTop": "10px"}),
        dcc.Graph(id="sim-graph"),
        html.H4("Apercu tabulaire"),
        dash_table.DataTable(
            id="sim-table",
            page_size=10,
            style_table={"overflowX": "auto"},
            style_cell={"fontFamily": "Consolas, monospace", "fontSize": 12, "textAlign": "left"},
        ),
        html.Div(style={"height": "120px"}),
    ]
)


@callback(
    Output("sim-select", "options"),
    Output("sim-select", "value"),
    Output("sim-status", "children"),
    Input("sim-onload-refresh", "n_intervals"),
)
def refresh_configs(_: int):
    options = _sim_options()
    if not options:
        return [], None, "Aucune configuration disponible. Cree-la d'abord dans Bibliotheque."
    return options, options[0]["value"], ""


@callback(
    Output("sim-yaml-store", "data"),
    Output("sim-mermaid-store", "data"),
    Output("sim-status", "children", allow_duplicate=True),
    Input("sim-select", "value"),
    prevent_initial_call=True,
)
def load_selected_yaml(selected_id: int | None):
    if selected_id is None:
        return "", "", "Selection vide."
    row = get_vessel_config(int(selected_id))
    if row is None:
        return "", "", "Configuration introuvable."
    try:
        cfg = yaml.safe_load(row.yaml_text)
        mermaid_chart = yaml_to_mermaid(cfg)
        status = f"Configuration chargee: {row.name}"
    except Exception as exc:  # noqa: BLE001
        err = str(exc).replace('"', "'")
        mermaid_chart = f'flowchart LR\n  err["Erreur Mermaid: {err}"]'
        status = f"Configuration chargee mais erreur Mermaid: {row.name}"
    return row.yaml_text, mermaid_chart, status


@callback(
    Output("sim-config-view", "children"),
    Input("sim-view-mode", "value"),
    Input("sim-yaml-store", "data"),
    Input("sim-mermaid-store", "data"),
)
def toggle_yaml_view(mode: str, yaml_text: str, mermaid_chart: str):
    if mode == "mermaid":
        return Mermaid(id="sim-mermaid-chart", chart=mermaid_chart or "flowchart LR\n  a[no_data]")
    return dcc.Textarea(
        id="sim-yaml",
        value=yaml_text or "",
        readOnly=True,
        style={"width": "100%", "height": "280px", "fontFamily": "Consolas, monospace"},
    )


@callback(
    Output("sim-status", "children", allow_duplicate=True),
    Output("sim-graph", "figure"),
    Output("sim-table", "data"),
    Output("sim-table", "columns"),
    Input("btn-run-sim", "n_clicks"),
    State("sim-yaml-store", "data"),
    State("sim-select", "value"),
    prevent_initial_call=True,
)
def run_simulation(_: int, yaml_text: str, selected_id: int | None):
    if selected_id is None:
        empty_fig = px.scatter(title="Simulation en attente")
        return "Selectionne une configuration avant de lancer.", empty_fig, [], []

    try:
        out = run_simulation_from_yaml(yaml_text)
        df = out.dataframe.copy()
        fig = _build_plot(df)
        data = df.head(200).to_dict("records")
        cols = [{"name": c, "id": c} for c in df.columns]
        status = f"Simulation OK: {out.n_rows} lignes, {len(out.columns)} colonnes."
        return status, fig, data, cols
    except Exception as exc:  # noqa: BLE001
        empty_fig = px.scatter(title="Simulation en echec")
        return f"Erreur: {exc}", empty_fig, [], []
