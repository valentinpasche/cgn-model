"""
Application Dash MVP (squelette).
"""

from __future__ import annotations

from dash import Dash, dcc, html, page_container

from services.db import init_db


def build_app() -> Dash:
    """
    Construit l'application Dash multi-pages.
    """
    init_db()

    app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True)
    app.title = "CGN Model - MVP Web"

    app.layout = html.Div(
        [
            html.H2("CGN Model - MVP Web"),
            dcc.Location(id="url"),
            html.Nav(
                [
                    dcc.Link("Accueil", href="/"),
                    " | ",
                    dcc.Link("Bibliotheque", href="/library"),
                    " | ",
                    dcc.Link("Builder YAML + DAG", href="/builder"),
                    " | ",
                    dcc.Link("Simulation", href="/simulation"),
                ]
            ),
            html.Hr(),
            page_container,
        ],
        style={"margin": "16px"},
    )
    return app


app = build_app()


if __name__ == "__main__":
    app.run(debug=True)
