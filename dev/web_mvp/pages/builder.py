"""
Page builder YAML + apercu DAG Mermaid.
"""

from __future__ import annotations

import yaml
from dash import Input, Output, callback, dcc, html, register_page

from services.dag_mermaid import yaml_to_mermaid
from services.default_yaml import load_default_yaml

register_page(__name__, path="/builder", name="Builder")


layout = html.Div(
    [
        html.H3("Builder guide (YAML + DAG)"),
        html.P("Edition YAML et generation d'un apercu DAG en format Mermaid."),
        dcc.Textarea(
            id="builder-yaml",
            value=load_default_yaml(),
            style={"width": "100%", "height": "360px", "fontFamily": "Consolas, monospace"},
        ),
        html.Br(),
        html.Button("Generer apercu DAG", id="btn-build-dag", n_clicks=0),
        html.Div(id="builder-error", style={"color": "#b00020", "marginTop": "10px"}),
        html.H4("Mermaid"),
        dcc.Markdown(id="builder-mermaid", style={"whiteSpace": "pre-wrap"}),
    ]
)


@callback(
    Output("builder-mermaid", "children"),
    Output("builder-error", "children"),
    Input("btn-build-dag", "n_clicks"),
    Input("builder-yaml", "value"),
)
def build_mermaid(_: int, yaml_text: str) -> tuple[str, str]:
    if not yaml_text or not yaml_text.strip():
        return "", "YAML vide."
    try:
        cfg = yaml.safe_load(yaml_text)
        mermaid = yaml_to_mermaid(cfg)
        return f"```mermaid\n{mermaid}\n```", ""
    except Exception as exc:  # noqa: BLE001
        return "", f"Erreur YAML/graph: {exc}"
