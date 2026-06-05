# Exemple d'utilisation en mode *script* : du YAML aux resultats

Ce document explique comment passer d'un YAML a un fichier de resultats.
L'objectif est de pouvoir recreer un script similaire a `examples/script_mode_260605/run.py`.

## Fichiers de l'exemple

Dossier : `examples/script_mode_260605`
- `config.yaml` : configuration du vessel et du solver.
- `run.py` : script pour utilisation normale.
- `run_detailed.py` : script complet pour une utilisation detaillee (chargement, simulation, export).
- `results.csv` : exemple de sortie CSV (valeurs reelles).

## Principe general

> Note: pour le guide complet de creation du YAML, voir [docs/yaml_guide.md](yaml_guide.md).

1) Le YAML decrit le vessel (profils, adaptateurs, inputs) et le solver (buses, convertisseurs).
2) `Vessel.from_yaml(...)` charge tout et prepare les objets.
3) `run()` prepare le solver, execute la resolution energetique et calcule les stockages.
4) `results_dataframe()` rassemble tout dans un DataFrame plat, avec unites dans les noms de colonnes.

## Configuration (YAML)

Le fichier `config.yaml` definit :
- Un profil de charge hoteliere constant (`hotel_load`).
- Un profil de vitesse derive des croisieres (`speed`).
- Deux adaptateurs :
  - vitesse -> puissance arbre (`shaft_power_from_speed`)
  - vitesse -> rendement du groupe (`eta_from_speed`)
- Deux inputs sur le solver : `shaft_demand` et `navops`.
- Trois buses (shaft, elec_power, fuel) et deux convertisseurs (motor, genset).
- Un storage `fuel_tank` sur le bus chimique.

## Script minimal

```python
from pathlib import Path

from cgn_model import Vessel

# Chargement de la configuration YAML.
example_dir = Path(__file__).resolve().parent
yaml_text = (example_dir / "config.yaml").read_text(encoding="utf-8")

# Construction de l'instance Vessel.
vessel = Vessel.from_yaml(yaml_text)

# Execution du workflow complet.
vessel.run()

# Extraction des resultats.
df = vessel.results_dataframe()

# Export optionnel.
cols = [
    "time_s",
    "profile_speed_m_per_s",
    "converter_motor_out_W",
    "storage_fuel_tank_v_stock_l",
]
df.to_csv(example_dir / "results.csv", sep=";", columns=cols, index=False)
```

## Conventions des colonnes

Le DataFrame renvoye par `results_dataframe()` utilise des noms plats avec suffixe d'unite :
- `time_s` pour le temps.
- Profils : `profile_<id>_<unite>` (ex. `profile_speed_m_per_s`).
- Adaptateurs : `adapter_<id>_<unite>` (ex. `adapter_eta_from_speed_unitless`)
- Inputs solver : `input_<id>_<unite>` (ex. `input_shaft_demand_W`).
- Convertisseurs : `converter_<id>_in_W` et `converter_<id>_out_W`.
- Stockages net : `storage_<id>_<base>_<unite>` (ex. `storage_fuel_tank_p_W`).
- Stockages niveau : `storage_<id>_<base>_stock_<unite>` (ex. `storage_fuel_tank_v_stock_m3`).

Rappel : les unites sont aussi disponibles dans `df.attrs["units"]`.

## Extrait de resultat (CSV)

Exemple sous forme de tableau :

| time_s | profile_speed_m_per_s | converter_motor_out_W | storage_fuel_tank_v_stock_l |
| --- | --- | --- | --- |
| 170.0 | 0.0 | 0.0 | 995.7 |
| 185.0 | 0.4 | 257.4 | 995.4 |
| 200.0 | 1.1 | 3248.9 | 995.1 |

## Erreurs frequentes

- Input ou convertisseur non calcule : appelez `vessel.run()` avant l'export.
- Résultats de stockage manquants : verifiez que les storages sont declares et que `vessel.run()` a ete appele.
- Nom de colonne introuvable : verifiez les IDs dans le YAML.

## Usage avance

Pour inspecter le solver entre les etapes, le workflow peut encore etre detaille :

```python
from cgn_model.energy_solver import run_vector

vessel.build_solver(verbose=True)
run_vector(vessel.solver)
vessel.tally_storages(require_solver_run=True)
```

Cet usage est utile pour le debogage ou pour modifier manuellement l'etat du
`SolverDAG`, mais il n'est pas necessaire dans le cas standard.
