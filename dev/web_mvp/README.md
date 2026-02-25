# MVP Web CGN Model (squelette)

Ce dossier contient un premier squelette d'interface web Dash pour le MVP.

Objectif de ce jalon:
- poser la structure de l'app;
- valider la boucle courte `YAML -> Vessel -> solver -> DataFrame`;
- afficher un apercu DAG en format Mermaid a partir du YAML.
- poser une base SQLite locale pour stocker les configurations YAML.

## Lancer localement

Prerequis (dans l'environnement conda du projet):
- `dash`
- `plotly`

Commande:

```powershell
python dev/web_mvp/app.py
```

Puis ouvrir: `http://127.0.0.1:8050`

## Etat du jalon

- Navigation multi-pages Dash.
- Page "Bibliotheque" CRUD minimale (SQLite).
- Edition YAML dans l'UI.
- Apercu DAG Mermaid genere depuis `buses` + `converters`.
- Execution solveur via APIs existantes (`Vessel.from_yaml`, `run_vector`).
- Table/graphique resultat minimal.

## Notes

- Le coeur physique du solver n'est pas modifie.
- Ce squelette est volontairement simple pour iterer vite pendant la semaine 1.
- La base SQLite est creee dans `dev/web_mvp/data/mvp.db`.
