"""Point d'entree UI V2 composants."""
#
# Lancement:
# - mode normal (stable): cgnmodel-gui
# - mode debug/dev:
#   - PowerShell: $env:CGN_GUI_DEBUG='1'; cgnmodel-gui
#   - CMD: set CGN_GUI_DEBUG=1 && cgnmodel-gui
# - desactiver l'ouverture auto navigateur:
#   - PowerShell: $env:CGN_GUI_OPEN_BROWSER='0'; cgnmodel-gui
#   - CMD: set CGN_GUI_OPEN_BROWSER=0 && cgnmodel-gui

from __future__ import annotations

import os
import webbrowser

from dash import Dash

from cgn_model.web_ui_v2.components_callbacks import register_callbacks
from cgn_model.web_ui_v2.components_layout import build_layout
from cgn_model.web_ui_v2.services.storage import init_db


init_db()
app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "CGN UI V2 - Composants"
app.layout = build_layout()
register_callbacks(app)

def _env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def open_browser() -> None:
    webbrowser.open_new("http://127.0.0.1:8050/")


def main():
    # Par defaut en mode stable (pas de hot-reload intempestif).
    # Override possible: CGN_GUI_DEBUG=1
    debug = _env_flag("CGN_GUI_DEBUG", default=False)
    auto_open_browser = _env_flag("CGN_GUI_OPEN_BROWSER", default=False)

    # Evite l'ouverture en double avec le reloader Flask/Werkzeug en mode debug.
    if auto_open_browser and (not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
        open_browser()

    app.run(debug=debug, host="127.0.0.1", port=8050)


if __name__ == "__main__":
    main()
