# Documentation CGN-model

Cette page est le point d'entrée de la documentation statique du modèle CGN.
Le `README.md` du dépôt reste destiné à l'installation rapide et aux commandes
de lancement. Cette documentation explique plutôt comment utiliser, configurer
et comprendre le modèle. Elle concerne principalement l'utilisation en mode
script et le fonctionnement interne du modèle ; les interfaces graphiques sont
traitées à part.

CGN-model est un package Python de simulation de chaîne énergétique pour bateau.
Il permet de décrire un scénario dans un fichier YAML, de générer les profils
nécessaires, de résoudre les flux d'énergie sur un graphe de bus et de
convertisseurs, puis d'exporter les résultats sous forme de tableau.

API utilisateur principale :

```python
from cgn_model import Vessel

vessel = Vessel.from_yaml(yaml_text)
vessel.run()
df = vessel.results_dataframe()
```

Les appels plus détaillés comme `build_solver()`, `run_vector()` ou
`tally_storages()` restent disponibles pour l'inspection et les usages avancés,
mais ils ne sont pas nécessaires pour l'utilisation courante.

## Notions À Connaître

Les termes suivants reviennent dans les guides. La référence complète est
disponible dans [Référence des modules, classes et notions principales](reference_modules_classes.md).

| Terme | Définition courte |
| --- | --- |
| `Vessel` | Objet principal qui orchestre la lecture YAML, les profils, le solveur et les résultats. |
| Profil | Signal temporel brut : constante, série, fichier CSV ou profil de navigation. |
| Adapter | Transformation d'un signal en un autre signal, par exemple vitesse vers puissance. |
| Input | Connexion d'un signal à un bus du solveur avec une convention de signe. |
| Bus | Nœud de bilan de puissance dans le solveur énergétique. |
| Converter | Convertisseur entre deux bus, avec un rendement constant ou variable. |
| DAG | Graphe orienté acyclique représentant la chaîne énergétique. |
| Storage | Post-traitement d'un bus pour calculer énergie cumulée, niveau, masse ou volume. |

## Parcours Conseillé

Pour une première prise en main :

1. Lire [Exemple d'utilisation en mode script](example_script.md) pour voir un
   calcul complet et directement exécutable.
2. Utiliser [Guide d'utilisation du modèle en mode script](script_guide.md) pour
   comprendre et modifier la configuration YAML.
3. Lire [Structure et déroulement du calcul](model_workflow.md) pour comprendre
   ce qui se passe entre `from_yaml()`, `run()` et `results_dataframe()`.
4. Consulter [Guide du module navigation](navigation_guide.md) si le scénario
   utilise un profil `kind: nav_speed` ou des horaires CGN.
5. Utiliser [Référence des modules, classes et notions principales](reference_modules_classes.md)
   pour retrouver rapidement le rôle d'un objet ou d'un module.

## Guides Disponibles

### Utilisation

- [Exemple d'utilisation en mode script](example_script.md) : exemple complet
  depuis un YAML jusqu'au CSV de résultats.
- [Guide d'utilisation du modèle en mode script](script_guide.md) : référence
  des sections YAML et fonctionnement du mode script.

### Compréhension Du Modèle

- [Structure et déroulement du calcul](model_workflow.md) : workflow interne,
  responsabilités des composants, états intermédiaires et limites actuelles.
- [Forward vs inverse](forward_vs_inverse.md) : explication des modes de
  résolution du solveur avec exemples numériques.
- [Référence des modules, classes et notions principales](reference_modules_classes.md) :
  glossaire transversal et cartographie simplifiée du code.

### Navigation

- [Guide du module navigation](navigation_guide.md) : données horaires CGN,
  structure des CSV, génération des profils de vitesse et paramètre
  `allow_delay`.

## Exemples De Référence

- [`examples/script_mode_260605/`](../examples/script_mode_260605/) : exemple
  principal en mode script avec `Vessel.run()` et workflow détaillé.
- [`examples/configurations_type_260605/`](../examples/configurations_type_260605/) :
  configurations types pour différentes architectures énergétiques.
- [`examples/solver_dag_mode_260605/`](../examples/solver_dag_mode_260605/) :
  exemple autonome utilisant uniquement `SolverDAG`, `prepare_state()` et
  `run_vector()`.

## Conventions Importantes

- Les scénarios sont décrits dans des fichiers YAML.
- Le pas de temps `simulation.dt` est exprimé en secondes.
- Les bus du solveur travaillent actuellement en puissance instantanée `W`.
- Les profils `nav_speed` utilisent les unités SI : vitesse en `m/s`,
  accélération et décélération en `m/s²`.
- Le mode recommandé du solveur est `inverse`.
- Les bus et convertisseurs du DAG doivent suivre le sens physique du flux
  d'énergie avec `from_bus -> to_bus`.
- Les inputs utilisent une convention de signe : `consume`, `inject` ou
  `as_is`.

## À Lire Ensuite Selon Le Besoin

- Pour modifier un YAML : [script_guide.md](script_guide.md).
- Pour comprendre les résultats et les colonnes : [example_script.md](example_script.md)
  puis [model_workflow.md](model_workflow.md).
- Pour inspecter ou compléter les horaires : [navigation_guide.md](navigation_guide.md).
- Pour comprendre un objet du code : [reference_modules_classes.md](reference_modules_classes.md).
- Pour inspecter directement le solveur : [`examples/solver_dag_mode_260605/`](../examples/solver_dag_mode_260605/).
