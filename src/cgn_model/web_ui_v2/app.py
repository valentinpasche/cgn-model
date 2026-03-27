"""Point d'entree UI V2 composants."""

from __future__ import annotations

from dash import Dash

from components_callbacks import register_callbacks
from components_layout import build_layout
from services.storage import init_db


init_db()
app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "CGN UI V2 - Composants"
app.layout = build_layout()
register_callbacks(app)


if __name__ == "__main__":
    app.run(debug=True)
