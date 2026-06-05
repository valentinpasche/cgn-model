# Structure et déroulement du calcul

Ce document décrit l'organisation générale du modèle CGN et le déroulement
interne d'une simulation. Il complète le guide d'utilisation en mode script :
le guide explique comment configurer le modèle, tandis que ce document explique
comment les données sont transformées et calculées.

L'objectif est de permettre à un utilisateur technique de comprendre :

- le rôle des principaux composants ;
- les étapes exécutées par `Vessel.from_yaml()` et `Vessel.run()` ;
- les données disponibles entre les étapes ;
- la séparation entre préparation métier, résolution énergétique et
  post-traitement.

## Vue d'ensemble

Le modèle transforme une configuration YAML et des données d'entrée en séries
temporelles de résultats.

```text
Configuration YAML
        |
        v
Vessel.from_yaml(...)
        |
        +--> validation et construction du SolverDAG
        +--> construction des profils
        +--> construction et application des adapters
        +--> matérialisation des signaux
        |
        v
Vessel.run()
        |
        +--> préparation des inputs du solveur
        +--> résolution du DAG énergétique
        +--> post-traitement des stockages
        |
        v
Vessel.results_dataframe()
        |
        v
DataFrame de résultats
```

Le workflow utilisateur principal reste volontairement court :

```python
from cgn_model import Vessel

vessel = Vessel.from_yaml(yaml_text)
vessel.run()
df = vessel.results_dataframe()
```

## Responsabilités principales

### Configuration YAML

Le YAML décrit un scénario de calcul. Il contient deux groupes d'informations :

- la partie métier, interprétée principalement par `Vessel` : profils,
  adapters, liaisons d'inputs et stockages ;
- la partie énergétique, interprétée par `SolverDAG` : bus, convertisseurs,
  inputs du solveur et mode de résolution.

Le YAML décrit les convertisseurs dans le sens physique du flux d'énergie, avec
`from_bus -> to_bus`, indépendamment de l'ordre utilisé pour résoudre le graphe.

### `Vessel`

`Vessel` est l'orchestrateur principal. Il traduit les données métier en signaux
numériques exploitables par le solveur, lance le calcul et rassemble les
résultats.

Il connaît notamment :

- le pas de temps `dt` ;
- les profils bruts ;
- les adapters et leurs sorties ;
- les conventions de signe des inputs ;
- la configuration des stockages ;
- le `SolverDAG` associé.

### `SolverDAG`

`SolverDAG` représente la chaîne énergétique sous forme de graphe orienté
acyclique :

- les bus sont les nœuds de bilan de puissance ;
- les convertisseurs sont les arêtes entre les bus ;
- les inputs ajoutent une demande ou une injection sur un bus.

Le solveur travaille actuellement avec des séries temporelles de puissances en
watts. Il ne connaît pas directement les notions de navigation, de profil de
vitesse ou de stockage métier.

### Profils et adapters

Les profils sont les données d'entrée brutes : constantes, séries explicites,
fichiers CSV ou profils de navigation.

Les adapters transforment ces profils en nouveaux signaux. Ils permettent par
exemple de convertir une vitesse en puissance arbre ou en rendement variable.
Les sorties d'adapters restent des grandeurs physiques non signées selon la
convention du solveur.

### Stockages

Les stockages sont calculés après la résolution. Ils intègrent le bilan de
puissance d'un bus pour produire une énergie cumulée et, lorsque les paramètres
nécessaires sont fournis, une masse, un volume ou un niveau restant.

Ils constituent un post-traitement : ils ne pilotent pas activement le solveur
et ne modifient pas les flux calculés.

## Étape 1 : chargement et validation

L'appel suivant démarre la construction du modèle :

```python
vessel = Vessel.from_yaml(yaml_text)
```

La configuration peut être fournie sous forme de texte YAML ou de dictionnaire
Python déjà chargé.

Plusieurs validations sont réalisées avant le calcul :

- structure et types des champs avec les modèles Pydantic ;
- présence des champs obligatoires ;
- unicité et collisions des identifiants ;
- existence des références entre profils, adapters, inputs et bus ;
- absence de cycle dans les dépendances des adapters ;
- absence de cycle dans le graphe énergétique ;
- cohérence des paramètres de stockage.

Le traitement est volontairement séparé :

1. `SolverDAG.from_yaml()` extrait et valide les sections énergétiques ;
2. `VesselSectionsCfg` valide les sections métier ;
3. `Vessel` contrôle les éventuelles collisions entre les deux ensembles.

Cette étape produit déjà un `SolverDAG` structuré, mais sans profils d'inputs
appliqués et sans flux résolus.

## Étape 2 : construction des objets runtime

Après validation, `Vessel.from_yaml()` construit les objets utilisés pendant la
simulation.

### Construction du `SolverDAG`

`SolverDAG.from_yaml()` :

1. construit les bus, inputs et convertisseurs ;
2. construit un graphe d'exécution contenant les bus et convertisseurs ;
3. construit un graphe de visualisation qui ajoute les inputs ;
4. vérifie que le graphe des convertisseurs est acyclique ;
5. détermine le plan ordonné d'exécution des convertisseurs.

En mode `inverse`, le plan parcourt les convertisseurs depuis les besoins aval
vers les sources amont.

### Construction des profils

Un profil maître fixe la longueur temporelle commune `N`.

- un profil `series`, `file` ou `nav_speed` peut fixer `N` ;
- une constante scalaire est répétée sur `N` pas de temps ;
- les autres profils doivent avoir une longueur compatible avec `N` ;
- aucune interpolation implicite n'est réalisée.

Chaque profil runtime contient un identifiant, une unité et un tableau
unidimensionnel.

### Construction et matérialisation des adapters

Les adapters sont instanciés depuis leur `kind` et leurs paramètres. Leurs
sorties sont ensuite calculées dans l'ordre imposé par leurs dépendances.

Un adapter n'est appliqué que lorsque toutes ses sources sont disponibles. Ce
fonctionnement permet d'enchaîner plusieurs transformations tout en détectant
les sources manquantes ou les cycles.

La matérialisation produit le mapping interne suivant :

```text
signal_id -> (série temporelle, unité)
```

Ce mapping, accessible via `vessel.signals`, contient à la fois les profils
bruts et les sorties d'adapters.

À la fin de `Vessel.from_yaml()`, les signaux métier sont donc déjà calculés. Le
solveur énergétique, lui, n'a pas encore été initialisé avec ses inputs.

## Étape 3 : préparation du solveur

Cette étape est exécutée par `Vessel.build_solver()`, appelé automatiquement par
`Vessel.run()`.

### Préparation des inputs

Pour chaque liaison déclarée dans `inputs`, `Vessel` :

1. récupère le signal référencé par `source` ;
2. vérifie qu'il est exprimé en watts, ou le convertit si l'option correspondante
   est activée ;
3. applique le facteur `scale` ;
4. applique la convention de signe ;
5. vérifie la cohérence entre l'input et son bus cible.

La convention numérique du solveur est :

```text
valeur positive = injection sur le bus
valeur négative = demande sur le bus
```

Les conventions YAML `consume`, `inject` et `as_is` sont traduites vers cette
représentation uniquement au moment de préparer le solveur. Les profils et
adapters restent ainsi indépendants de leur usage comme consommation ou
injection.

### Initialisation de l'état numérique

`prepare_state()` initialise le solveur :

- les profils signés sont attachés aux inputs ;
- chaque `bus.net_w` est initialisé puis alimenté par ses inputs ;
- les contributions sont enregistrées dans les ledgers (registres) des bus ;
- les résultats précédents des convertisseurs sont réinitialisés ;
- la longueur temporelle commune est vérifiée.

À ce stade, `bus.net_w` représente le bilan initial créé par les inputs, avant
propagation entre les bus.

### Rendements variables

Lorsqu'un convertisseur `variable_eta` référence un `eta_source`, le signal
adimensionnel correspondant est attaché automatiquement au convertisseur.

Par défaut, ce profil est borné dans l'intervalle admissible afin d'éviter un
rendement nul ou supérieur à un. Si aucun profil n'est attaché, le convertisseur
utilise son `eta_default`.

## Étape 4 : résolution du DAG

`Vessel.run()` appelle ensuite `run_vector(vessel.solver)`.

La résolution est vectorielle : chaque opération porte directement sur
l'ensemble des pas de temps, plutôt que d'exécuter une boucle de simulation
complète pas par pas.

### Mode inverse

Le mode `inverse` est le mode de référence actuel. Pour chaque convertisseur,
dans l'ordre défini par le plan :

1. le solveur observe le déficit du bus aval ;
2. ce déficit définit la puissance de sortie requise du convertisseur ;
3. la méthode inverse du convertisseur calcule la puissance nécessaire en
   entrée en tenant compte du rendement ;
4. la puissance d'entrée est retirée du bus amont ;
5. la puissance de sortie est ajoutée au bus aval.

Exemple simplifié :

```text
demande mécanique aval : 90 kW
rendement du moteur     : 0,90
besoin électrique amont : 90 / 0,90 = 100 kW
```

Le solveur remonte ainsi la chaîne énergétique depuis les demandes vers les
sources nécessaires.

Les résultats calculés sont enregistrés dans :

- `bus.net_w` pour le bilan final de chaque bus ;
- `converter.p_in_w` pour la puissance d'entrée des convertisseurs ;
- `converter.p_out_w` pour leur puissance de sortie ;
- les ledgers des bus pour tracer les contributions.

Le mode `forward` existe dans la structure du code, mais son exécution est
actuellement protégée par une erreur explicite tant qu'il n'a pas été validé sur
un cas physique de référence.

## Étape 5 : post-traitement des stockages

Après la résolution, `Vessel.run()` appelle `tally_storages()`.

Pour chaque stockage déclaré, le modèle :

1. récupère le `net_w` du bus associé ;
2. sépare les composantes positives et négatives ;
3. intègre la puissance avec le pas de temps `dt` ;
4. calcule l'énergie cumulée ;
5. applique éventuellement un niveau initial ;
6. réalise les conversions en masse ou volume lorsque le PCI et la densité le
   permettent.

Cette étape produit des objets `StorageResult`. Elle ne relance pas le solveur et
ne modifie pas le comportement énergétique du scénario.

## Étape 6 : préparation des résultats

`Vessel.results_dataframe()` rassemble les séries disponibles dans un
`pandas.DataFrame`.

Le DataFrame peut contenir :

- le vecteur temps ;
- les profils bruts ;
- les sorties d'adapters ;
- les inputs signés du solveur ;
- les puissances d'entrée et de sortie des convertisseurs ;
- les résultats de stockage.

Les noms de colonnes sont préfixés selon leur origine :

```text
profile_<id>_<unité>
adapter_<id>_<unité>
input_<id>_W
converter_<id>_in_W
converter_<id>_out_W
storage_<id>_<grandeur>_<unité>
```

Les unités sont également conservées dans `df.attrs["units"]`.

Un filtre `ids` permet aussi d’extraire uniquement certains résultats disponibles.
Un ID de convertisseur ou de stockage sélectionne automatiquement l’ensemble de ses colonnes associées.

## États successifs du modèle

Le tableau suivant résume les données disponibles après chaque appel principal.

| Après l'appel | Signaux métier | Inputs du solveur | Flux convertisseurs | Stockages | DataFrame complet |
| --- | --- | --- | --- | --- | --- |
| `Vessel.from_yaml()` | disponibles | non appliqués | non calculés | non calculés | non |
| `vessel.build_solver()` | disponibles | appliqués | initialisés, non résolus | non calculés | non |
| `run_vector(vessel.solver)` | disponibles | appliqués | calculés | non calculés | non |
| `vessel.tally_storages()` | disponibles | appliqués | calculés | calculés | oui |
| `vessel.run()` | disponibles | appliqués | calculés | calculés | oui |

Si aucun stockage n'est configuré, l'étape correspondante est naturellement
vide.

## Workflow détaillé

L'usage détaillé décompose explicitement les opérations normalement prises en
charge par `Vessel.run()` :

Un exemple exécutable complet est disponible dans
[`run_detailed.py`](../examples/script_mode_260605/run_detailed.py).

```python
from cgn_model import Vessel
from cgn_model.energy_solver import run_vector

vessel = Vessel.from_yaml(yaml_text)

vessel.build_solver(verbose=True)
run_vector(vessel.solver)
vessel.tally_storages(require_solver_run=True)

df = vessel.results_dataframe()
```

Ce niveau de contrôle est utile pour :

- inspecter les signaux avant leur application au solveur ;
- vérifier les inputs signés et les bus ciblés ;
- examiner le DAG et son plan d'exécution ;
- modifier ou contrôler un état intermédiaire ;
- déboguer une configuration ou un nouveau composant.

Pour l'utilisation courante, `Vessel.run()` reste préférable afin de garantir
l'ordre correct des opérations.

## Contrôles et erreurs détectées

Les contrôles sont répartis au plus près de l'étape concernée :

- Pydantic valide la forme et les types de la configuration ;
- `VesselSectionsCfg` contrôle les dépendances et identifiants métier ;
- `SolverDAG` contrôle les bus, convertisseurs et cycles du graphe ;
- la construction des profils contrôle la longueur temporelle `N` ;
- les adapters contrôlent leurs paramètres, unités et sources ;
- la préparation des inputs contrôle les watts, signes et bus cibles ;
- `prepare_state()` contrôle les dimensions des séries ;
- `results_dataframe()` contrôle la disponibilité et la cohérence des résultats.

Cette organisation vise à produire une erreur proche de sa cause, avant qu'une
configuration incohérente ne génère silencieusement des résultats.

## Limites du workflow actuel

Le déroulement décrit repose sur plusieurs choix assumés :

- les bus du solveur travaillent actuellement en watts ;
- le calcul est vectoriel et essentiellement statique à chaque pas de temps ;
- le graphe énergétique doit être acyclique ;
- le mode `inverse` est le seul mode validé pour l'usage courant ;
- les stockages sont des post-traitements et non des composants activement
  pilotés ;
- les coefficients empiriques et leurs domaines de validité restent sous la
  responsabilité de l'utilisateur.

Ces limites permettent de conserver un workflow déterministe, traçable et
adapté aux analyses énergétiques macroscopiques visées par le modèle.
