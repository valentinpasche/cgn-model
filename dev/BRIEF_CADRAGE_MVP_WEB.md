# Brief de cadrage - nouvelle session Codex (MVP web)

## Objectif
Construire une interface web operationnelle pour `cgn-model`, utilisable par un client sans IDE.

## Delai
- 2 a 3 semaines (MVP strict).
- Priorite: fonctionnalite et stabilite, pas de sur-ingenierie UI.

## Perimetre MVP (in)
- CRUD composants et bateaux/configurations.
- Builder guide (liste + formulaire) pour construire la chaine energetique.
- Graphe DAG d'apercu auto-mis a jour.
- Synchronisation immediate: edition composant -> graphe + YAML + validations.
- Import/export YAML.
- Parametrage simulation.
- Execution solver.
- Visualisation resultats et export CSV (XLSX option si temps).

## Hors perimetre (out)
- Editeur DAG drag-and-drop complet.
- Creation no-code de nouveaux types d'equations physiques.
- Gestion multi-utilisateur avancee.

## Choix techniques retenus
- UI: Dash.
- Persistance MVP: SQLite en mode single-writer.
- Option d'evolution: PostgreSQL si besoin de multi-ecriture simultanee.
- Format modele: YAML (contrat avec le solver existant).
- Principe: ne pas reecrire le moteur de calcul, reutiliser les APIs actuelles.

## Entrees techniques du projet
- `cgn_model.energy_solver.SolverDAG.from_yaml`
- `cgn_model.energy_solver.prepare_state`
- `cgn_model.energy_solver.run_vector`
- `cgn_model.vessel_model.Vessel.from_yaml`
- `cgn_model.navigation.Croisiere`

## Fichiers a lire en priorite
- `AGENTS.md`
- `dev/CLIENT_MVP_PROPOSITION.md`
- `dev/NOTE_CADRAGE_MVP_DETAILLEE.md`
- `docs/yaml_guide.md`
- `docs/example_v1.md`
- `src/cgn_model/vessel_model/vessel.py`
- `src/cgn_model/energy_solver/solver_dag.py`
- `src/cgn_model/energy_solver/run_dag.py`

## Regles de pilotage
- Travailler par jalons hebdo Go/No-Go.
- Si retard: couper en priorite les options UI et XLSX.
- Garder la compatibilite YAML/solver comme contrainte forte.
