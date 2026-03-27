"""Point d'entree UI V2 composants."""

from __future__ import annotations

from dash import Dash

from cgn_model.web_ui_v2.components_callbacks import register_callbacks
from cgn_model.web_ui_v2.components_layout import build_layout
from cgn_model.web_ui_v2.services.storage import init_db


init_db()
app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "CGN UI V2 - Composants"
app.layout = build_layout()
register_callbacks(app)


def main() -> None:
    app.run(debug=True)


if __name__ == "__main__":
    main()
