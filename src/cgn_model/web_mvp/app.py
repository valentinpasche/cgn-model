"""Point d'entree interface web MVP."""
#
# Lancement:
# - mode normal (stable): cgnmodel-mvp
# - mode debug/dev:
#   - PowerShell: $env:CGN_MVP_DEBUG='1'; cgnmodel-mvp
#   - CMD: set CGN_MVP_DEBUG=1 && cgnmodel-mvp
# - ouverture auto navigateur:
#   - PowerShell: $env:CGN_MVP_OPEN_BROWSER='1'; cgnmodel-mvp
#   - CMD: set CGN_MVP_OPEN_BROWSER=1 && cgnmodel-mvp
# - reactiver les logs serveur en mode stable:
#   - PowerShell: $env:CGN_MVP_QUIET='0'; cgnmodel-mvp
#   - CMD: set CGN_MVP_QUIET=0 && cgnmodel-mvp

from __future__ import annotations

import logging
import os
import webbrowser

from dash import Dash, dcc, html, page_container

from cgn_model.web_mvp.services.db import db_path, init_db


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
                        "MVP realise pour `CGN Model` - credits: V. Pasche (HEIA-FR) + R. Baur (CGN)",
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


def _env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def open_browser() -> None:
    webbrowser.open_new("http://127.0.0.1:8050/")


def main() -> None:
    # Par defaut en mode stable (pas de hot-reload intempestif).
    # Override possible: CGN_MVP_DEBUG=1
    debug = _env_flag("CGN_MVP_DEBUG", default=False)
    auto_open_browser = _env_flag("CGN_MVP_OPEN_BROWSER", default=False)
    quiet = _env_flag("CGN_MVP_QUIET", default=not debug)
    url = "http://127.0.0.1:8050/"

    if quiet:
        logging.getLogger("werkzeug").setLevel(logging.ERROR)

    # Evite l'ouverture en double avec le reloader Flask/Werkzeug en mode debug.
    if auto_open_browser and (not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
        open_browser()

    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        print(f"Interface CGN MVP disponible sur {url}", flush=True)
        print(f"Base SQLite utilisee: {db_path()}", flush=True)

    app.run(debug=debug, host="127.0.0.1", port=8050)


if __name__ == "__main__":
    main()


