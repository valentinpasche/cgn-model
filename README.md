# CGN - Modèle de simulation chaîne énergétique

---

## 🔧 Installation

### Via le fichier `environment.yml` (à privilégier, essentiellement)

> 1. Cloner le dépôt GitHub
> 2. En ligne de commande (conda) : se placer à la racine du repo, là où se trouve le fichier `environment.yml`
> 3. Executer les commandes suivantes :

```bash
conda env create -f environment.yml
conda activate cgnmodel
python -c "import cgn_model; print('OK:', cgn_model.__name__, 'version:', getattr(cgn_model, '__version__', '?'))"
```

## ▶️ Utilisation classique, via Spyder

Lancer l'application spyder depuis l'environnement **cgnmodel**

```bash
conda activate cgnmodel
spyder
```

Ou directement l'application de bureau : *Spyder 6 (cgnmodel)*

---

Notes de developpement : voir dev/notes_objectifs.md.
