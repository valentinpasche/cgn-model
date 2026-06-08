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
        html.H3("Lectures conseillées"),
        html.P("Documentation principale du projet :"),
        html.Ul(
            [
                html.Li([
                    "Documentation CGN-model",
                    html.Br(),
                    "  docs/index.md",
                    html.Br(),
                    html.Br(),
                ]),
                html.Li([
                    "Exemple d'utilisation en mode script",
                    html.Br(),
                    "  docs/example_script.md",
                    html.Br(),
                    html.Br(),
                ]),
                html.Li([
                    "Guide d'utilisation du modèle en mode script",
                    html.Br(),
                    "  docs/script_guide.md",
                    html.Br(),
                    html.Br(),
                ]),
                html.Li([
                    "Guide du module navigation",
                    html.Br(),
                    "  docs/navigation_guide.md",
                ]),
            ]
        ),
    ]
)