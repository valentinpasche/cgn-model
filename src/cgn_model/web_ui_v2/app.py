"""Point d'entree UI V2 composants."""

from __future__ import annotations

import os
import webbrowser
from threading import Timer

from dash import Dash

from cgn_model.web_ui_v2.components_callbacks import register_callbacks
from cgn_model.web_ui_v2.components_layout import build_layout
from cgn_model.web_ui_v2.services.storage import init_db


init_db()
app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "CGN UI V2 - Composants"
app.layout = build_layout()
register_callbacks(app)


def open_browser():
    webbrowser.open_new("http://127.0.0.1:8050/")


def main():
    debug = True

    # Evite l'ouverture en double avec le reloader Flask/Werkzeug
    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        Timer(1, open_browser).start()

    app.run(debug=debug, host="127.0.0.1", port=8050)


if __name__ == "__main__":
    main()
