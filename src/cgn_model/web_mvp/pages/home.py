"""
Page d'accueil MVP.
"""

from dash import html, register_page

register_page(__name__, path="/", name="Accueil")


layout = html.Div(
    [
        html.H3("Objectif MVP"),
        html.Ul(
            [
                html.Li("Configurer un modele YAML sans IDE."),
                html.Li("Visualiser le DAG de configuration."),
                html.Li("Executer le solver et consulter les resultats."),
            ]
        ),
        html.P("Prochain jalon: CRUD composants/bateaux + persistance SQLite."),
    ]
)
