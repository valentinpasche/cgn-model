"""
Page d'execution simulation (YAML en lecture seule).
"""

from __future__ import annotations

import pandas as pd
import yaml
from dash import Input, Output, State, callback, dash_table, dcc, html, register_page
from dash_extensions import Mermaid
import plotly.express as px
import plotly.graph_objects as go

from cgn_model.web_mvp.services.dag_mermaid import yaml_to_mermaid
from cgn_model.web_mvp.services.db import get_vessel_config, list_vessel_configs
from cgn_model.web_mvp.services.simulation import run_simulation_from_yaml

register_page(__name__, path="/simulation", name="Simulation")


def _sim_options() -> list[dict[str, str | int]]:
    rows = list_vessel_configs()
    return [{"label": r.name, "value": r.id} for r in rows]


def _build_profiles_plot(df: pd.DataFrame, profile_cols: list[str]):
    time_col = "time_s" if "time_s" in df.columns else None
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    y_cols = [c for c in profile_cols if c in numeric_cols]

    if not y_cols:
        if time_col and len(numeric_cols) > 1:
            fallback = [next((c for c in numeric_cols if c != time_col), numeric_cols[0])]
        elif numeric_cols:
            fallback = [numeric_cols[0]]
        else:
            fig = px.scatter(title="Aucune serie numerique exploitable")
            fig.update_layout(autosize=True, margin={"l": 40, "r": 20, "t": 50, "b": 40})
            return fig
        y_cols = fallback

    fig = go.Figure()
    if time_col:
        x_values = df[time_col]
        x_title = time_col
    else:
        x_values = df.index
        x_title = "index"

    colors = px.colors.qualitative.Plotly
    n = len(y_cols)
    left_count = (n + 1) // 2
    right_count = n // 2

    left_band = min(max(0.10, 0.05 * left_count), 0.30)
    right_band = min(max(0.10, 0.05 * right_count), 0.30)
    x_domain = [left_band, 1.0 - right_band]

    def _positions(count: int, start: float, end: float) -> list[float]:
        if count <= 0:
            return []
        if count == 1:
            return [(start + end) / 2]
        step = (end - start) / (count - 1)
        return [start + i * step for i in range(count)]

    left_positions = _positions(left_count, 0.02, max(0.02, left_band - 0.02))
    right_positions = _positions(right_count, min(0.98, 1.0 - right_band + 0.02), 0.98)
    left_idx = 0
    right_idx = 0

    for i, col in enumerate(y_cols):
        color = colors[i % len(colors)]
        axis_ref = "y" if i == 0 else f"y{i+1}"
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=df[col],
                mode="lines",
                name=col,
                showlegend=True,
                yaxis=axis_ref,
                line={"color": color},
            )
        )

        axis_key = "yaxis" if i == 0 else f"yaxis{i+1}"
        side = "left" if i % 2 == 0 else "right"
        if side == "left":
            position = left_positions[left_idx]
            left_idx += 1
        else:
            position = right_positions[right_idx]
            right_idx += 1

        axis_cfg = {
            "title": {"text": col, "font": {"color": color}},
            "tickfont": {"color": color},
            "side": side,
            "showgrid": i == 0,
            "zeroline": False,
        }

        if i == 0:
            axis_cfg["anchor"] = "x"
        else:
            axis_cfg["overlaying"] = "y"
            axis_cfg["anchor"] = "free"
            axis_cfg["position"] = position

        fig.update_layout(**{axis_key: axis_cfg})

    fig.update_layout(
        autosize=True,
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
        showlegend=True,
        legend_title_text="Courbes",
        legend={
            "orientation": "v",
            "x": 1.02,
            "xanchor": "left",
            "y": 1.0,
            "yanchor": "top",
        },
        xaxis_title=x_title,
        xaxis={"domain": x_domain},
    )
    return fig


def _profile_columns_from_yaml(df: pd.DataFrame, yaml_text: str) -> list[str]:
    """
    Retourne les colonnes du DataFrame correspondant aux profils YAML.
    """
    try:
        cfg = yaml.safe_load(yaml_text) or {}
    except Exception:  # noqa: BLE001
        return []

    profiles = cfg.get("profiles", []) or []
    profile_ids = [str(p.get("id", "")).strip() for p in profiles if isinstance(p, dict)]
    profile_ids = [pid for pid in profile_ids if pid]

    cols: list[str] = []
    for pid in profile_ids:
        prefix = f"{pid}_"
        matched = [c for c in df.columns if c.startswith(prefix)]
        for col in matched:
            if col not in cols:
                cols.append(col)
    return cols


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
        html.Div(
            [
                dcc.Graph(
                    id="sim-graph",
                    responsive=True,
                    style={"width": "100%", "height": "100%"},
                    config={"responsive": True},
                )
            ],
            style={
                "resize": "both",
                "overflow": "auto",
                "width": "100%",
                "minWidth": "420px",
                "height": "420px",
                "minHeight": "260px",
                "maxHeight": "80vh",
                "border": "1px solid #d1d5db",
                "borderRadius": "8px",
                "padding": "6px",
                "background": "#fff",
            },
        ),
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
        cfg_name = "inconnue"
        vessel_name = "inconnu"
        row = get_vessel_config(int(selected_id))
        if row is not None:
            cfg_name = row.name
        try:
            parsed_yaml = yaml.safe_load(yaml_text) or {}
            vessel_name = str((parsed_yaml.get("vessel") or {}).get("name") or "inconnu")
        except Exception:  # noqa: BLE001
            pass

        out = run_simulation_from_yaml(yaml_text)
        df = out.dataframe.copy()
        profile_cols = _profile_columns_from_yaml(df, yaml_text)
        fig = _build_profiles_plot(df, profile_cols)
        fig.update_layout(
            title={
                "text": (
                    f"Simulation energetique - Configuration : {cfg_name}"
                    f"<br><sup>Vessel: {vessel_name}</sup>"
                )
            }
        )
        data = df.head(200).to_dict("records")
        cols = [{"name": c, "id": c} for c in df.columns]
        status = (
            f"Simulation OK: {out.n_rows} lignes, {len(out.columns)} colonnes, "
            f"{len(profile_cols)} profil(s) affiche(s)."
        )
        return status, fig, data, cols
    except Exception as exc:  # noqa: BLE001
        empty_fig = px.scatter(title="Simulation en echec")
        return f"Erreur: {exc}", empty_fig, [], []
