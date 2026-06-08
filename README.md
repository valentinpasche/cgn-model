# CGN-model

CGN-model est un package Python de simulation de chaîne énergétique pour bateau.
Il permet de décrire un scénario en YAML, de calculer les flux d'énergie sur un
graphe de bus et de convertisseurs, puis d'exporter les résultats sous forme de
tableau.

La documentation principale est disponible ici :

- [Documentation CGN-model](docs/index.md)
- [Exemple d'utilisation en mode script](docs/example_script.md)
- [Guide d'utilisation du modèle en mode script](docs/script_guide.md)
- [Guide du module navigation](docs/navigation_guide.md)

## Installation

Le projet n'est pas publié sur PyPI. L'installation se fait depuis un clone du
dépôt ou depuis un ZIP de release/tag.

### Installation standard

```bash
conda env create -f environment.yml
conda activate cgnmodel
pip install .
```

Vérification :

```bash
python -c "import cgn_model; print('OK:', cgn_model.__name__, 'version:', getattr(cgn_model, '__version__', '?'))"
```

### Installation en développement

Utiliser le mode éditable si le code doit être modifié localement :

```bash
conda env create -f environment.yml
conda activate cgnmodel
pip install -e .
```

## Utilisation En Mode Script

L'API principale est :

```python
from cgn_model import Vessel

vessel = Vessel.from_yaml(yaml_text)
vessel.run()
df = vessel.results_dataframe()
```

Exemple complet :

```bash
python examples/script_mode_260605/run.py
```

## Interfaces Graphiques

Avant de lancer une interface, activer l'environnement Conda du projet :

```bash
conda activate cgnmodel
```

Commandes disponibles après installation :

```bash
cgnmodel-gui
cgnmodel-mvp
```

`cgnmodel-gui` lance l'interface principale actuelle. `cgnmodel-mvp` correspond à
une interface plus ancienne/conservée comme prototype.

### Bases De Données Des Interfaces

Les interfaces graphiques utilisent des bases SQLite locales pour enregistrer
les configurations et les composants créés depuis l'UI.

Seuls les fichiers templates sont versionnés dans le dépôt GitHub :

- `src/cgn_model/web_ui_v2/data/ui_v2_template.db`
- `src/cgn_model/web_mvp/data/mvp_template.db`

Les bases utilisées à l'exécution ne sont pas versionnées. Elles restent propres
à chaque installation locale et peuvent donc être gérées indépendamment :

- `src/cgn_model/web_ui_v2/data/ui_v2.db`
- `src/cgn_model/web_mvp/data/mvp.db`

Avant la première utilisation d'une interface, créer la base correspondante en
copiant le template puis en supprimant le suffixe `_template` dans le nom du
fichier. Par exemple :

```text
ui_v2_template.db -> ui_v2.db
mvp_template.db   -> mvp.db
```

Cette logique permet aussi d'archiver localement une base de données : il suffit
de renommer le fichier `.db` utilisé, puis de recréer une base propre depuis le
template. L'interface utilise toujours le fichier portant le nom attendu
(`ui_v2.db` ou `mvp.db`).

### Lancement Windows Par Fichier `.bat`

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

Dans certains environnements d'entreprise, l'exécution des fichiers `.bat` peut
être bloquée. Dans ce cas, utiliser directement les commandes terminal ci-dessus.

## Utilisation Avec Spyder

Lancer Spyder depuis l'environnement `cgnmodel` :

```bash
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
