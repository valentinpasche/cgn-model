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
            html.Div(
                [
                    html.Img(
                        src="/assets/CGN_logo.svg",
                        alt="CGN logo",
                        style={"height": "34px", "width": "auto"},
                    ),
                    html.P(
                        "MVP realise pour CGN Model - credits: equipe projet + client",
                        style={"margin": 0, "fontWeight": 600},
                    ),
                    html.Div(
                        [
                            html.Img(
                                src="/assets/SeSi_logo.svg",
                                alt="HEIA-FR logo",
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
            ),
        ],
        style={"margin": "16px", "paddingBottom": "32px"},
    )
    return app


app = build_app()


if __name__ == "__main__":
    app.run(debug=True)
