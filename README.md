# CGN - Modele de simulation chaine energetique

## Installation

Le projet n'est pas publie sur PyPI. Pour une installation "standard", utilisez un ZIP de release/tag,
créez l'environnement Conda, puis installez le package localement.

### Installation standard (release ZIP)

1) Telecharger une release/tag (ZIP) et dezipper.
2) Ouvrir un terminal dans le dossier du projet.
3) Creer l'environnement, puis installer le package.

```bash
conda env create -f environment.yml
conda activate cgnmodel
pip install .

python -c "import cgn_model; print('OK:', cgn_model.__name__, 'version:', getattr(cgn_model, '__version__', '?'))"
```

### Installation developpement (meme environment.yml)

Deux options equivalentes :
- **Cloner le repo** (recommande pour contribuer)
- **Utiliser un ZIP de release** si vous voulez modifier localement une version figée

Dans les deux cas :

```bash
conda env create -f environment.yml
conda activate cgnmodel
pip install -e .

python -c "import cgn_model; print('OK:', cgn_model.__name__, 'version:', getattr(cgn_model, '__version__', '?'))"
```

## Quickstart

- Guide YAML : voir [docs/yaml_guide.md](docs/yaml_guide.md)
- Exemple complet V1 : voir [docs/example_v1.md](docs/example_v1.md)
- Navigation (nav_speed) : voir [docs/navigation_guide.md](docs/navigation_guide.md)

## Utilisation (Spyder)

Lancer Spyder depuis l'environnement **cgnmodel** :

```bash
conda activate cgnmodel
spyder
```

Notes de developpement : voir `dev/notes_objectifs.md`.