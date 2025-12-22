# Exemple V1 : du YAML aux resultats

Ce document explique comment utiliser l'exemple V1 pour passer d'un YAML a un fichier de resultats.
L'objectif est de pouvoir recreer un script similaire a `examples/cgn_model_v1_251222/demo_v1.py` (hors affichage graphique).

## Fichiers de l'exemple

Dossier : `examples/cgn_model_v1_251222`
- `config_v1.yaml` : configuration du vessel et du solver.
- `demo_v1.py` : script complet (chargement, simulation, export).
- `demo_v1_results.csv` : exemple de sortie CSV (valeurs reelles).

## Principe general

> Note: pour le guide complet de creation du YAML, voir [docs/yaml_guide.md ↗](yaml_guide.md).

1) Le YAML decrit le vessel (profils, adaptateurs, inputs) et le solver (buses, convertisseurs).
2) `Vessel.from_yaml(...)` charge tout et prepare les objets.
3) `build_solver()` attache les profils aux inputs du solver et fixe la taille N.
4) `run_vector(...)` execute la resolution energetique.
5) `tally_storages()` calcule les indicateurs des stockages.
6) `results_dataframe()` rassemble tout dans un DataFrame plat, avec unites dans les noms de colonnes.

## Configuration (YAML)

Le fichier `config_v1.yaml` definit :
- Un profil de charge hoteliere constant (`hotel_load`).
- Un profil de vitesse derive des croisieres (`speed`).
- Deux adaptateurs :
  - vitesse -> puissance arbre (`shaft_power_from_speed`)
  - vitesse -> rendement du groupe (`eta_from_speed`)
- Deux inputs sur le solver : `shaft_demand` et `navops`.
- Trois buses (shaft, elec_power, fuel) et deux convertisseurs (motor, genset).
- Un storage `fuel_tank` sur le bus chimique.

## Script minimal (sans affichage)

Copiez ce script dans un fichier Python place dans le dossier de l'exemple.

```python
import yaml
from cgn_model.vessel_model import Vessel
from cgn_model.energy_solver import run_vector

# 1) Charger le YAML
with open("config_v1.yaml", "r") as f:
    cfg = yaml.safe_load(f)

# 2) Construire le Vessel
vessel = Vessel.from_yaml(cfg)

# 3) Cabler les inputs (prepare le solver)
vessel.build_solver(verbose=True)

# 4) Lancer la resolution
run_vector(vessel.solver)

# 5) Calculer les stockages
vessel.tally_storages()

# 6) Recuperer les resultats
df = vessel.results_dataframe()

# Exemple : calcul simple de volume cumule de carburant
pci = 35.28e9  # J/m3
if "fuel_tank_e_cum_J" in df.columns:
    df["fuel_cum_m3"] = df["fuel_tank_e_cum_J"] / pci

# 7) Export CSV
cols = [
    "time_s",
    "speed_m_per_s",
    "hotel_load_W",
    "motor_out_W",
    "genset_out_W",
    "fuel_tank_p_W",
    "fuel_tank_e_cum_J",
    "fuel_cum_m3",
]

# Filtrer uniquement si les colonnes existent
cols = [c for c in cols if c in df.columns]

# df[cols].to_csv("demo_v1_results.csv", sep=";", index=False)
```

## Conventions des colonnes

Le DataFrame renvoye par `results_dataframe()` utilise des noms plats avec suffixe d'unite :
- `time_s` pour le temps.
- Signaux et inputs : `<id>_<unite>` (ex. `speed_m_per_s`, `shaft_demand_W`).
- Convertisseurs : `<id>_in_W` et `<id>_out_W`.
- Stockages : `<storage>_<base>_<unite>` (ex. `fuel_tank_p_W`, `fuel_tank_e_cum_J`).

Rappel : les unites sont aussi disponibles dans `df.attrs["units"]`.

## Extrait de resultat (CSV)

Exemple d'extrait sous forme de tableau (arrondi pour la lisibilite) :

| time_s | speed_m_per_s | hotel_load_W | motor_out_W | genset_out_W | fuel_tank_p_W | fuel_tank_e_cum_J | fuel_cum_m3 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0 | 0.0 | 100000.0 | 0.0 | 100000.0 | -897803.1 | -897803.1 | -2.5448e-05 |
| 1.0 | 0.0 | 100000.0 | 0.0 | 100000.0 | -897803.1 | -1795606.2 | -5.0896e-05 |
| 2.0 | 0.0 | 100000.0 | 0.0 | 100000.0 | -897803.1 | -2693409.2 | -7.6344e-05 |

## Erreurs frequentes

- Input non cable : appelez `build_solver()` avant `run_vector()`.
- Vecteurs manquants : appelez `tally_storages()` avant l'export si des storages sont declares.
- Nom de colonne introuvable : verifiez les IDs dans le YAML.