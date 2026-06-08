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
