# Guide navigation (profils nav_speed)

Ce document explique ou trouver les fichiers CSV de navigation et comment selectionner une croisiere/course/etape  
pour un profil **`kind: nav_speed`**.

## Ou sont les CSV

Les CSV embarques sont dans :
- `src/cgn_model/navigation/data/cgn_croisieres/`

Le fichier principal est :
- `all.csv`

Dans le YAML, on reference un CSV via :
- `source: "cgn_croisieres/<name>"`
  - ex. `cgn_croisieres/all` charge `all.csv`.

## Structure d'un CSV

Colonnes attendues (separees par `;`) :
- `croisiere` (str)
- `course` (int)
- `port` (str)
- `horaire` (str, format `HHhMM`)
- `km` (float)
- `minutes` (float)

Extrait :
```text
croisiere;course;port;horaire;km;minutes
translemanique;101;Lausanne;10h55;5;20
;;St-Sulpice;11h15;6;18
```

Regles simples :
- les valeurs de `croisiere` et `course` sont propagees vers le bas si vides.
- une ligne i et la ligne i+1 definissent une etape (depart -> arrivee).
- `km = 0` indique une pause.

## Selection dans le YAML (nav_speed)

Dans la section `profiles` :
- `select.by: "cruise"` + `cruise_name: <str>`
- `select.by: "course"` + `course_no: <int>`
- `select.by: "leg"` + `leg: {from_port: <str>, to_port: <str>}`

Ces valeurs correspondent aux noms contenus dans le CSV.

## Parametres de vitesse (SpeedProfileParams)

Champs principaux (si non fournis, valeurs par defaut) :
- `dt` : pas de temps [s]
- `acc` / `dec` : acceleration / deceleration [m/s^2]
- `v_croisiere` : vitesse cible [m/s]
- `v_moyenne_horaire` : optionnel, controle macro de la vitesse moyenne [m/s]
- `allow_delay` : si false, le profil doit respecter strictement l'horaire

Exemple YAML :
```yaml
- id: "speed"
  kind: "nav_speed"
  unit: "m/s"
  source: "cgn_croisieres/all"
  select:
    by: "cruise"
    cruise_name: "Lavaux - Haut-Lac"
  params:
    acc: 0.05
    dec: 0.05
    v_croisiere: 7.0
    allow_delay: true
```

## Utilisation directe du module navigation
Les objets exposes (Croisiere, Course, Etape) proposent plusieurs proprietes utiles
(temps, distance, vitesse moyenne, etc.). Un guide plus detaille pourra etre ajoute plus tard.

Deux methodes pratiques pour charger des horaires hors du `Vessel` :
- `Croisiere.from_cgn_croisiere_csv("all")` charge un CSV embarque du package
  (le nom est sans extension, ex. `all` -> `all.csv`).
- `Croisiere.from_csv("mon_fichier.csv")` charge un CSV local.

Exemple :
```python
from cgn_model.navigation import Croisiere

# CSV embarque (package)
croisieres = Croisiere.from_cgn_croisiere_csv("all")

# Affichage simple (utile pour verifier / copier des noms pour le YAML)
for c in croisieres:
    print(c)  # ou Croisiere.view_croisiere(c)
```

## Ajouter un nouveau CSV

1) Ajouter un fichier `<name>.csv` dans `src/cgn_model/navigation/data/cgn_croisieres/`.
2) Respecter les colonnes et le separateur `;`.
3) Utiliser `source: "cgn_croisieres/<name>"` dans le YAML.
4) Verifier rapidement la continuite et l'affichage :

```python
from cgn_model.navigation import Croisiere

croisieres = Croisiere.from_csv("mon_fichier.csv")

for c in croisieres:
    assert c.check_continuite()
    Croisiere.view_croisiere(c)
```