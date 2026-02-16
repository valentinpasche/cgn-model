# Proposition MVP Web - cgn-model (Document client)

## 1. Objectif
Mettre à disposition une interface web opérationnelle permettant d'utiliser les fonctionnalités existantes de `cgn-model` sans IDE, via navigateur, dans une logique MVP (délai cible: 2-3 semaines).

## 2. Résultat attendu (MVP)
Le MVP permettra de:
- créer et modifier une configuration énergétique de bateau via interface;
- générer/importer/exporter un fichier YAML de modèle;
- sélectionner un bateau et associer une ou plusieurs courses;
- définir les paramètres de simulation (ex: pas de temps, vitesse de croisière);
- lancer le calcul et visualiser les résultats;
- choisir les sorties à afficher et exporter en CSV (XLSX en option selon validation technique).

## 3. Architecture proposée (pragmatique)
- Interface web: **Dash** (Python)
- Moteur de calcul: bibliothèque existante **`cgn-model`**
- Données métier persistantes: **SQLite** (choix retenu MVP, mode single-writer)
- Option d'évolution: **PostgreSQL** si besoin de multi-écriture simultanée ou montée en charge
- Modèles de simulation: **YAML** (import/export)

Principe:
- l'utilisateur manipule des formulaires et listes;
- l'application construit/valide le YAML en arrière-plan;
- le solver est exécuté avec ce YAML;
- les résultats sont affichés (graph/table) et exportables.

## 4. Pourquoi ce choix
- Le navigateur répond au besoin d'usage sans IDE.
- Dash offre un bon compromis entre rapidité de développement et qualité d'interface.
- SQLite évite la complexité d'une infra DB lourde tout en restant robuste pour un démarrage simple.
- PostgreSQL apporte une base partagée plus robuste pour un usage depuis plusieurs postes et une montée en charge.
- YAML reste le format naturel de configuration, traçable et partageable.

## 5. Choix de stockage côté client
### Choix retenu - SQLite (MVP rapide)
- Avantage: très simple, fichier local unique (`.db`), pas de serveur DB à administrer.
- Cas d'usage: petite équipe, accès depuis plusieurs postes en lecture et écriture non simultanée.
- Mode d'exploitation recommandé: **single-writer** (un seul utilisateur écrit à un instant donné).
- Limite: moins adapté à la collaboration régulière multi-postes en écriture concurrente.

### Option d'évolution - PostgreSQL (si nécessaire)
- Intérêt: base centralisée robuste pour multi-écriture simultanée et usage intensif.
- Déclencheur: besoin réel de concurrence d'écriture ou d'industrialisation plus poussée.

### Recommandation de trajectoire
- Démarrer en **SQLite** pour accélérer le MVP.
- Préparer la migration en utilisant **SQLAlchemy + Alembic** dès le départ.
- Basculer vers **PostgreSQL** via changement d'URL de connexion et migration du schéma/données.

## 6. Périmètre MVP vs hors périmètre
### Inclus dans le MVP
- CRUD de composants (créer, modifier, supprimer) au niveau configuration.
- CRUD de bateaux/configurations.
- "Équiper un bateau" via un builder guidé (sélection de composants + connexions logiques).
- Graphe DAG d'aperçu mis à jour automatiquement au fil de la configuration.
- Liste/table des composants du graphe pour navigation et contrôle.
- Formulaire d'édition des composants (ids, bus, paramètres) avec mise à jour immédiate du graphe, du YAML et des validations.
- Association bateau ↔ course(s) via fichiers de course externes.
- Paramétrage de simulation.
- Exécution calcul.
- Visualisation et export.

### Hors périmètre MVP (phase 2)
- Éditeur graphique full drag-and-drop avancé de DAG.
- Système plugin/no-code pour écrire de nouvelles équations physiques dans l'interface.
- Gestion multi-utilisateur avancée (rôles, audit complet, etc.).
- Dispatch énergétique avancé sur configurations non triviales (au-delà des contraintes actuelles de la logique DAG).

## 7. Planning indicatif (2-3 semaines)
Hypothèse: périmètre figé, arbitrages rapides et une itération principale de retours utilisateur.

1. Semaine 1
- structure app Dash;
- modèle de données (SQLite, compatible migration PostgreSQL);
- import/export YAML;
- écrans CRUD composants/bateaux.

2. Semaine 2
- builder guidé de chaîne énergétique;
- association courses;
- paramètres de simulation;
- exécution solver.

3. Semaine 3
- visualisations avancées;
- export CSV (XLSX en option);
- stabilisation, validation utilisateur, documentation d'usage.

## 8. Risques et limites (transparents)
- Le drag-and-drop complet de DAG peut dépasser le délai MVP.
- La création de nouvelles lois/équations restera côté Python au départ.
- Les performances dépendront de la taille des simulations (à valider avec jeux de données réels).
- Une stratégie SQLite "copier-coller de fichier" fonctionne pour un besoin très basique, mais peut générer des conflits de version de données.
- Certaines configurations énergétiques avancées restent contraintes par l'approche de résolution actuelle (DAG), et peuvent nécessiter une évolution du solveur en phase 2.

## 9. Critères d'acceptation MVP
- Un utilisateur non développeur peut configurer un bateau, lancer une simulation et exporter les résultats sans IDE.
- Les modèles sont sauvegardables/rechargeables.
- Les sorties clés sont visualisables et exportables.

## 10. Décision proposée
Valider un **MVP web Dash** en 2-3 semaines, avec:
- **choix MVP**: SQLite + YAML en mode single-writer;
- **option d'évolution**: PostgreSQL + YAML si multi-postes avec écritures simultanées;
- extension possible vers un éditeur visuel avancé en phase 2.
