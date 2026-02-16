# Note détaillée - cadrage interface web cgn-model (historique et options)

## 1. Contexte et besoin initial
Objectif exprimé:
- rendre `cgn-model` utilisable par un client sans IDE;
- gérer les entrées/sorties via interface;
- conserver la logique actuelle basée sur YAML et solver existant;
- livrer rapidement (2-3 semaines).

Contraintes:
- délai court;
- nécessité d'un outil opérationnel avant toute montée en complexité;
- préférence pour une application navigateur.

## 2. Options étudiées (synthèse)

| Option | Vitesse MVP | Flexibilité UI | Compatibilité réseau entreprise | Niveau risque planning | Commentaire |
|---|---:|---:|---:|---:|---|
| Streamlit | Très élevée | Moyenne | Moyenne | Faible | Très rapide pour un POC/MVP simple |
| Dash | Élevée | Élevée | Élevée | Moyen | Meilleur compromis rendu/flexibilité |
| NiceGUI | Élevée | Moyenne | Moyenne | Moyen | Bonne productivité, écosystème plus restreint |
| PyQt/wx (desktop) | Moyenne | Élevée | Très élevée | Moyen/élevé | Packaging plus lourd, moins "browser-first" |
| FastAPI + React | Faible (dans ce délai) | Très élevée | Très élevée | Élevé | Excellente cible long terme, trop ambitieux en 2-3 semaines |

Décision recommandée:
- **Dash** comme cible MVP web;
- **Streamlit** comme plan B si la pression planning devient critique.

## 3. Rôle de Dash, SQLite/PostgreSQL et YAML

### Dash (interface web)
Dash sert à construire:
- pages de gestion (composants, bateaux, courses, simulations);
- formulaires de paramètres;
- tables filtrables;
- graphes interactifs (Plotly);
- boutons d'actions (import/export/lancement calcul).

### SQLite ou PostgreSQL (stockage applicatif)
SQLite ou PostgreSQL stockent:
- bibliothèque de composants réutilisables;
- bateaux/configurations référencées;
- presets de simulation;
- historique minimal des runs (optionnel MVP mais utile).

Choix retenu pour le MVP client:
- **SQLite** en mode **single-writer** (écritures non simultanées).
- PostgreSQL reste une option d'évolution si la concurrence d'écriture devient un besoin réel.

Variante SQLite (MVP simple):
- pas d'infrastructure serveur DB à maintenir;
- fichier `.db` unique, très simple à démarrer;
- pertinent pour un besoin basique (ex: accès de plusieurs collègues, avec écritures non simultanées).
- recommandation forte: éviter la multi-écriture directe sur partage réseau SMB (risques de verrouillage/corruption selon usage et infrastructure).
- pratique recommandée: gérer un mode single-writer explicite dans l'application (message "base occupée" + retry).

Variante PostgreSQL (MVP robuste):
- base centralisée accessible depuis plusieurs postes;
- meilleure robustesse et évolutivité;
- adaptée à un usage entreprise avec partage de données durable.

### YAML (format de modèle)
Le YAML reste:
- le format de description des modèles énergétiques;
- le format import/export utilisateur;
- le "contrat" avec le solver existant.

Pourquoi pas un "immense YAML" comme DB principale:
- difficile à faire évoluer (indexation, concurrence, historique, validation partielle);
- plus risqué pour la qualité des données à moyen terme.

Principe retenu:
- **SQLite ou PostgreSQL = catalogue/persistance applicative**;
- **YAML = fichier de configuration simulable et échangeable**.

Bonne pratique d'implémentation:
- utiliser **SQLAlchemy** (et migrations **Alembic**) pour garder une compatibilité forte SQLite/PostgreSQL;
- privilégier des modèles et requêtes portables (éviter SQL spécifique moteur tant que possible);
- permettre la bascule via URL de connexion (`sqlite:///...` vs `postgresql+psycopg://...`).

## 4. Couverture détaillée des besoins MVP

| Besoin utilisateur | Méthode UI proposée | Données utilisées | Sortie/effet |
|---|---|---|---|
| Créer/modifier/supprimer des composants | Formulaire + table avec actions "éditer/supprimer" | SQLite/PostgreSQL (`components`) | Composants disponibles en bibliothèque |
| Créer/modifier/supprimer des bateaux | Formulaire + table "bateaux" | SQLite/PostgreSQL (`vessels`) | Configurations réutilisables |
| Équiper un bateau avec composants | Builder guidé: liste de composants + écran de connexions | SQLite/PostgreSQL + logique app | Structure de chaîne prête à transformer en YAML |
| Générer le YAML | Bouton "Générer/Valider" + aperçu texte | Données builder + paramètres | Fichier YAML valide pour solver |
| Importer YAML existant | Upload fichier + validation | YAML utilisateur | Pré-remplissage UI + sauvegarde optionnelle |
| Exporter YAML | Bouton export | Modèle courant | Téléchargement YAML |
| Sélectionner un bateau | Liste déroulante/recherche | SQLite/PostgreSQL (`vessels`) | Chargement configuration en session |
| Associer une/des courses | Sélecteur multi-courses + table d'association | Fichiers course + SQLite/PostgreSQL (`races`) | Simulation contextualisée |
| Paramètres simulation | Formulaire (pas de temps, vitesse, etc.) | Session + presets SQLite/PostgreSQL | Entrées pour exécution solver |
| Lancer calcul | Bouton "Run" + barre statut | YAML + paramètres | Résultats tabulaires/séries temporelles |
| Choisir sorties à afficher | Multi-sélection de colonnes/signaux | Résultats run | Graphe et table filtrés |
| Export CSV/XLSX | Boutons d'export | Résultats sélectionnés | Fichier CSV (XLSX en option) |

## 5. Niveau visuel DAG: cible réaliste MVP
Niveau MVP recommandé:
- édition **semi-visuelle guidée** (liste + connexions + aperçu graphe);
- validation des liens (noms bus I/O, doublons, cohérence).
- graphe DAG d'aperçu mis à jour automatiquement à chaque modification utilisateur.
- pilotage par une liste/table des composants, avec formulaire d'édition (ids, bus, paramètres).
- synchronisation immédiate: modification composant -> mise à jour graphe + YAML + validations.

Niveau phase 2:
- drag-and-drop complet de nœuds/arêtes;
- édition graphique avancée.

Cette approche réduit fortement le risque planning tout en gardant la logique systémique compréhensible.

## 6. Intégration avec `cgn-model`
Entrées techniques majeures déjà identifiées:
- `cgn_model.energy_solver.SolverDAG.from_yaml`
- `cgn_model.energy_solver.prepare_state`
- `cgn_model.energy_solver.run_vector`
- `cgn_model.vessel_model.Vessel.from_yaml`
- `cgn_model.navigation.Croisiere`

Pipeline applicatif:
1. l'UI collecte/sauvegarde la configuration;
2. l'app génère ou charge le YAML;
3. le backend appelle le solver;
4. les résultats sont transformés pour affichage/export.

## 7. Estimation charge et risque

| Bloc | Charge estimée | Risque |
|---|---|---|
| Fondations Dash + structure pages | 2-3 jours | Faible |
| DB + modèles CRUD (SQLite, compatible PostgreSQL) | 2-3 jours | Faible |
| Builder guidé chaîne énergétique | 3-5 jours | Moyen |
| Import/export YAML + validation | 1-2 jours | Faible |
| Exécution solver + gestion erreurs | 2-3 jours | Moyen |
| Visualisation + export CSV (XLSX option) | 2-3 jours | Faible |
| Stabilisation + tests utilisateur | 3-4 jours | Moyen |

Fenêtre globale cohérente: **2-3 semaines**.
Hypothèse de validité: périmètre stabilisé en début de réalisation, arbitrages rapides, et une itération principale de retours.

## 8. Limites fonctionnelles à expliciter au client
- Le MVP ne remplace pas l'édition Python pour créer de nouvelles équations/lois physiques.
- L'outil cible d'abord l'opérationnel courant (configurer/simuler/analyser), pas le développement avancé du modèle.
- L'éditeur DAG complet interactif est une amélioration ultérieure.
- Une organisation par simple copie de fichier SQLite peut fonctionner au début, mais reste fragile dès que les allers-retours entre postes deviennent fréquents.
- Certaines topologies/configurations avancées peuvent rester limitées par l'approche de résolution actuelle (DAG) et nécessiter une évolution solveur dédiée.

## 9. Proposition de trajectoire
1. Valider rapidement le périmètre MVP (fonctionnel, non exhaustif).
2. Réaliser un démonstrateur Dash en fin de semaine 1.
3. Itérer avec retours client sur ergonomie.
4. Préparer la phase 2 selon usage réel observé.

## 10. Note de cadrage planning (pilotage recommandé)

Pour sécuriser la fenêtre 2-3 semaines, piloter avec des jalons "Go/No-Go":

1. Fin semaine 1 (Go/No-Go 1)
- pages de base + CRUD principaux opérationnels;
- import/export YAML fonctionnels;
- schéma DB validé (SQLite, compatible migration PostgreSQL).

2. Fin semaine 2 (Go/No-Go 2)
- chaîne complète exécutable sur un cas réel:
  chargement configuration -> génération/validation YAML -> run solver -> affichage résultats.
- gestion d'erreurs utilisateur minimale (messages clairs).

3. Fin semaine 3 (stabilisation)
- exports CSV validés (XLSX seulement si temps disponible);
- corrections UX majeures;
- validation utilisateur finale + documentation d'usage.

Marge recommandée:
- prévoir 15-20% de contingence (intégration UI/solver, retours ergonomie, bugs de dernière minute).

Definition of Done MVP:
- un utilisateur non développeur réalise un scénario complet sans IDE:
  sélectionner/créer une config, lancer le calcul, visualiser et exporter les résultats CSV.
