# AGENTS.md

Ce fichier sert de guide pour travailler avec Codex (ou d'autres agents) dans ce repo.

## Qu'est-ce qu'un runbook / des conventions ?
- Runbook : une check-list d'actions reproductibles (ex. "comment lancer une démo", "comment valider un changement").
- Conventions : règles de style/organisation (ex. langue du code, structure des dossiers).

## Conventions du projet
- Code : anglais autant que possible (noms, commentaires, variables).
- Documentation / docstrings : français.
- Unités : SI dans le solver (W, s, m/s) sauf mention contraire.

## Points d'entrée utiles
- Solver DAG : `cgn_model.energy_solver.SolverDAG.from_yaml`
- Exécution : `cgn_model.energy_solver.prepare_state`, `cgn_model.energy_solver.run_vector`
- Orchestrateur métier : `cgn_model.vessel_model.Vessel.from_yaml`
- Navigation : `cgn_model.navigation.Croisiere`

## Runbook (template)
### Installer l'environnement
- `conda env create -f environment.yml`
- `conda activate cgnmodel`

### Lancer une démo
- Exemple solver DAG : `python examples/demo_solver_dag.py`
- Exemple "copil" : `python examples/cgn_copil_251212/copil_251212_inputs_calcul.py`

### Tests / validation rapide
- `pytest` (si tu veux un run global)
- Tests ciblés : `python tests/test_croisieres.py`

## Notes pour les agents
- Ne pas modifier les données `src/cgn_model/navigation/data/...` sans demande explicite.
- Les scripts `dev/` sont exploratoires, pas des API publiques.
- Priorité : stabilité du solveur et du schéma YAML.
