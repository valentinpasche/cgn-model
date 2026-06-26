# CGN-model

CGN-model est un package Python de simulation de chaîne énergétique pour bateau.
Il permet de décrire un scénario en YAML, de calculer les flux d'énergie sur un
graphe de bus et de convertisseurs, puis d'exporter les résultats sous forme de
tableau.

La documentation principale est disponible ici :

- [Documentation CGN-model](docs/index.md)
- [Guide des interfaces graphiques](docs/gui_guide.md)
- [Exemple d'utilisation en mode script](docs/example_script.md)
- [Guide d'utilisation du modèle en mode script](docs/script_guide.md)
- [Guide du module navigation](docs/navigation_guide.md)

## Installation

Le projet n'est pas publié sur PyPI. L'installation se fait depuis un clone du
dépôt GitHub ou depuis un ZIP de release/tag.

L'installation recommandée utilise Conda et le fichier `environment.yml`. Cet
environnement correspond à l'environnement de référence utilisé pour développer
et tester le projet.

Les principales dépendances installées sont notamment `numpy`, `pandas`,
`pydantic`, `PyYAML`, `networkx`, `dash`, `plotly` et les composants Dash utilisés
par les interfaces graphiques. La liste complète et les versions de référence
sont définies dans `environment.yml`.

### 1. Installer Anaconda ou Miniconda

Si la commande `conda` n'est pas déjà disponible sur la machine, installer une
distribution qui fournit Conda, par exemple Anaconda ou Miniconda.

Documentation officielle :

- Anaconda : <https://docs.anaconda.com/anaconda/install/>
- Miniconda : <https://www.anaconda.com/docs/getting-started/miniconda/install>
- Concepts Conda : <https://docs.conda.io/projects/conda/en/stable/user-guide/>

Un environnement Conda permet d'isoler les librairies Python du projet. Cela
évite que les dépendances de CGN-model entrent en conflit avec celles d'autres
projets Python installés sur la même machine. Il permet aussi d'installer un
ensemble cohérent de versions compatibles entre elles, plutôt que d'ajouter les
paquets manuellement un par un.

Sous Windows, les commandes ci-dessous sont à exécuter dans **Anaconda Prompt**
ou dans un terminal où la commande `conda` est disponible.

### 2. Ouvrir le dossier du projet

Depuis le terminal, se placer dans le dossier racine du projet, c'est-à-dire le
dossier qui contient notamment `environment.yml` et `pyproject.toml`.

Exemple :

```cmd
cd C:\chemin\vers\cgn-model
```

### 3. Créer l'environnement Conda

```cmd
conda env create -f environment.yml
```

Cette commande installe Python et les dépendances nécessaires au projet. Les
paquets à installer sont listés dans `environment.yml`; ils ne doivent
normalement pas être installés manuellement un par un.

Le fichier `environment.yml` utilise le canal `conda-forge`, afin de résoudre les
dépendances depuis une source cohérente et reproductible.

### 4. Activer l'environnement

```cmd
conda activate cgnmodel
```

Après activation, le nom de l'environnement doit apparaître au début de la ligne
de commande :

```text
(cgnmodel) C:\...>
```

### 5. Installer le package CGN-model

```cmd
python -m pip install --no-deps .
```

Dans cette procédure recommandée, Conda installe les dépendances depuis
`environment.yml`, puis `pip` installe uniquement le package local CGN-model.
L'option `--no-deps` évite que `pip` modifie les dépendances déjà installées par
Conda.

### 6. Vérifier l'installation

Vérifier d'abord que les dépendances Python sont cohérentes :

```cmd
python -m pip check
```

Vérifier ensuite que le package est importable :

```cmd
python -c "import cgn_model; print('OK:', cgn_model.__name__, 'version:', getattr(cgn_model, '__version__', '?'))"
```

Il est aussi possible d'afficher les paquets installés dans l'environnement actif :

```cmd
conda list
```

Si les commandes de vérification s'exécutent sans erreur, l'installation de base
est prête.

### Installation en développement

Si le code doit être modifié localement, utiliser le mode éditable :

```cmd
conda env create -f environment.yml
conda activate cgnmodel
python -m pip install --no-deps -e .
```

### Installation alternative via `pip`

Une installation directe via `pip` peut fonctionner si Conda n'est pas utilisable :

```cmd
python -m pip install .
```

ou, en mode éditable :

```cmd
python -m pip install -e .
```

Cette méthode utilise les dépendances déclarées dans `pyproject.toml`. Elle peut
être utile comme solution alternative, mais elle n'est pas l'environnement de
référence du projet. Le fonctionnement validé correspond à l'environnement Conda
défini dans `environment.yml`.

### En cas de problème d'installation

Si une erreur du type `ModuleNotFoundError` apparaît juste après la création de
l'environnement, cela indique généralement que l'environnement n'a pas été créé
correctement ou que certaines dépendances n'ont pas été installées.

Points à vérifier :

- l'environnement `cgnmodel` est bien activé ;
- les commandes sont exécutées depuis le dossier racine du projet ;
- l'accès au dépôt `conda-forge` n'est pas bloqué par le réseau, un proxy ou une
  règle informatique interne ;
- l'installation n'a pas été faite dans l'environnement `base` par erreur.

Installer les dépendances une par une avec `pip install ...` peut dépanner
ponctuellement, mais ce n'est pas la procédure de référence et cela ne garantit
pas les mêmes versions que l'environnement testé.

## Utilisation en mode script

L'API principale est :

```python
from cgn_model import Vessel

vessel = Vessel.from_yaml(yaml_text)
vessel.run()
df = vessel.results_dataframe()
```

Exemple complet :

```cmd
python examples/script_mode_260605/run.py
```

Voir aussi : [Exemple d'utilisation en mode script](docs/example_script.md).

## Interfaces graphiques

Les commandes ci-dessous sont à exécuter dans Anaconda Prompt ou dans un terminal
où la commande `conda` est disponible, comme pour l'installation.

Avant de lancer une interface, activer l'environnement Conda du projet :

```cmd
conda activate cgnmodel
```

Commandes disponibles après installation :

```cmd
cgnmodel-gui
cgnmodel-mvp
```

`cgnmodel-gui` lance l'interface principale actuelle. `cgnmodel-mvp` correspond à
une interface plus ancienne, conservée comme prototype.

Au démarrage, l'interface affiche dans le terminal l'adresse locale à ouvrir dans
le navigateur et le chemin de la base SQLite utilisée.

Les bases SQLite utilisateur sont créées automatiquement au premier lancement
à partir de fichiers templates inclus dans le package. Elles sont placées dans
un dossier local, par défaut :

```text
%LOCALAPPDATA%\CGN-model\
```

La documentation détaillée des interfaces, des bases SQLite et des variables
d'environnement est disponible ici : [Guide des interfaces graphiques](docs/gui_guide.md).

### Lancement Windows par fichier `.bat`

Sous Windows, [Lancer_CGN_GUI.bat](Lancer_CGN_GUI.bat) peut lancer l'interface
graphique principale.

Avant de l'utiliser, vérifier le chemin de Conda dans le fichier :

```bat
%UserProfile%\miniconda\condabin\conda.bat
```

Selon l'installation, il peut être nécessaire de remplacer `miniconda` par
`Miniconda3`, `anaconda3`, ou par un chemin explicite comme :

```bat
C:\Users\<Utilisateur>\miniconda3\condabin\conda.bat
```

## Utilisation avec Spyder

Lancer Spyder depuis l'environnement `cgnmodel` :

```cmd
conda activate cgnmodel
spyder
```

Sous Windows, Spyder peut aussi être lancé directement depuis l'exécutable créé
dans l'environnement Conda. Exemple à adapter selon l'installation :

```text
C:\Users\<Utilisateur>\miniconda\envs\cgnmodel\Scripts\spyder.exe
```

Cet exécutable utilise directement l'interpréteur Python de l'environnement
`cgnmodel`.

## Exemples

- [`examples/script_mode_260605/`](examples/script_mode_260605/) : exemple
  principal en mode script.
- [`examples/configurations_type_260605/`](examples/configurations_type_260605/) :
  configurations types.
- [`examples/solver_dag_mode_260605/`](examples/solver_dag_mode_260605/) :
  exemple autonome du solveur `SolverDAG`.
