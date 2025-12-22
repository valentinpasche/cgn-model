# Guide YAML (config d'entree)

Ce document explique comment definir un fichier YAML d'entree pour le modele CGN.
Le YAML relie des profils (inputs), des adapters (transformations), des inputs du solver,
les bus d'energie et les convertisseurs du DAG.

## Vue d'ensemble du modele
> Note: pour un exemple complet (YAML + script), voir `docs/example_v1.md`.
- Le solveur (energy_solver) calcule les bilans d'energie sur un DAG de bus + convertisseurs.
- Les profils (profiles) sont des signaux bruts (vitesse, charges, etc.).
- Les adapters transforment ces profils (ex. vitesse -> puissance) et produisent des signaux en W.
- Les inputs lient un signal (profile/adapter) a un bus du solver avec une convention de signe.
- Les convertisseurs (converters) transfèrent l'energie entre bus avec un rendement.
- Les storages (optionnel) permettent de post-traiter un bus comme un stockage (bilan energie/puissance).

Flux logique :
profiles -> adapters -> inputs -> solver (buses + converters) -> run_vector -> (optionnel) storages

Note importante :
- Le DAG (buses + converters) doit suivre le sens physique du flux d'energie (from_bus -> to_bus).
- En dehors du DAG, les adapters suivent la convention de nommage (ex. speed_to_power_poly).

## Sections du YAML

### vessel
Metadonnees du bateau.

Champs :
- name (str) : nom du bateau
- vessel_type (str) : "DE" | "steam" | "undefined"
- type (str) : alias de vessel_type (ne pas fournir les deux avec des valeurs differentes)

Exemple :
```yaml
vessel:
  name: "Vevey"
  vessel_type: "DE"
```

### simulation
Parametres globaux.

Champs :
- dt (float, > 0) : pas de temps [s]

Exemple :
```yaml
simulation:
  dt: 1.0
```

### profiles
Declaration des profils bruts.

Champs communs :
- id (str) : identifiant unique
- kind (str) : "constant" | "series" | "file" | "nav_speed"
- unit (str) : unite declaree
- master (bool, optionnel) : profil maitre (definit N)

#### kind = constant
Champs :
- value (float | list[float]) : valeur constante (len=1) ou serie de taille N

Exemple :
```yaml
- id: "hotel_load"
  kind: "constant"
  unit: "W"
  value: 100000
```

#### kind = series
Champs :
- data (list[float]) : serie explicite

Exemple :
```yaml
- id: "speed"
  kind: "series"
  unit: "m/s"
  data: [0.0, 1.2, 2.5, 3.0]
  master: true
```

#### kind = file
Champs :
- file (str) : chemin vers un CSV
- column (str | null) : colonne a lire (optionnel)
- sep (str | null) : separateur CSV (",", ";", "\t", "|")
- decimal (str) : "." ou ","
- encoding (str) : encodage (defaut "utf-8-sig")

Exemple :
```yaml
- id: "speed"
  kind: "file"
  unit: "m/s"
  file: "speed_vector_ms.csv"
  column: "speed_ms"
  master: true
```

#### kind = nav_speed
Construit un profil de vitesse a partir des horaires CGN embarques.
Si allow_delay = false, le profil doit respecter strictement l'horaire (sinon erreur).

Champs :
- source (str) : "cgn_croisieres/<name>" (ex. "cgn_croisieres/all")
- select (dict) : selection par croisiere / course / etape
  - by: "cruise" | "course" | "leg"
  - cruise_name (str) si by="cruise"
  - course_no (int) si by="course"
  - leg: {from_port: str, to_port: str} si by="leg"
- params (dict, optionnel) : parametres MRUA
  - acc (float)
  - dec (float)
  - v_croisiere (float)
  - allow_delay (bool)

Exemple :
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
  master: true
```

### adapters
Transformations de profils (ex. vitesse -> puissance).

Champs :
- id (str) : identifiant unique
- kind (str) : voir liste des kinds plus bas
- source (str) : id d'un profile ou d'un adapter (ignore pour multi-entrees)
- unit_in (str) : unite attendue en entree
- unit_out (str) : unite de sortie
- params (dict) : parametres du kind

Notes :
- Pour les adapters multi-entrees, source et unit_in sont ignores mais doivent etre renseignes
  (pour satisfaire le schema Pydantic).

Exemple (vitesse -> puissance, poly) :
```yaml
- id: "shaft_power_from_speed"
  kind: "speed_to_power_poly"
  source: "speed"
  unit_in: "m/s"
  unit_out: "W"
  params:
    coeffs: [0.0, -209.0, 1904.4, 531.36, 93.312]
```

### inputs
Liaison d'un signal (profile/adapter) vers un input du solver.

Champs :
- id (str) : id de l'input (cote solver)
- bus (str) : bus cible (cote solver)
- source (str) : id d'un profile ou d'un adapter
- sign (str) : "consume" | "inject" | "as_is"
- scale (float, optionnel) : facteur multiplicatif

Exemple :
```yaml
- id: "shaft_demand"
  bus: "Mechanical:shaft"
  source: "shaft_power_from_speed"
  sign: "consume"
```

### solver
Champs :
- mode (str) : "inverse" | "forward" (forward non valide pour l'instant)

Exemple :
```yaml
solver:
  mode: "inverse"
```

### buses
Declaration des bus du solver.

Champs :
- id (str)
- carrier (str) : "Electrical" | "Mechanical" | "Chemical" (ou autre)
- unit (str, optionnel) : W (par defaut)

Exemple :
```yaml
buses:
  - id: "Mechanical:shaft"
    carrier: "Mechanical"
  - id: "Electrical:main"
    carrier: "Electrical"
  - id: "Chemical:fuel"
    carrier: "Chemical"
```

### converters
Convertisseurs du solver (transfert d'energie entre bus).

Champs :
- id (str)
- from_bus (str)
- to_bus (str)
- kind (str) : voir liste des kinds plus bas
- params (dict) : parametres du kind

Exemple (rendement constant) :
```yaml
converters:
  - id: "genset"
    from_bus: "Chemical:fuel"
    to_bus: "Electrical:main"
    kind: "constant_eta"
    params:
      eta: 0.38
```

### storages (optionnel)
Declaration de bus a post-traiter en stockage.

Champs :
- id (str)
- bus (str)
- vecteur (str | null) : identifiant du vecteur (diesel, H2, battery)

Exemple :
```yaml
storages:
  - id: "fuel_tank"
    bus: "Chemical:fuel"
    vecteur: "diesel"
```

## Kinds disponibles

### Adapters
- speed_to_power_poly
  - params: {coeffs: list[float], clip_min: float | None}
- force_and_speed_to_power
  - params: {force_source, speed_source, force_unit_in, speed_unit_in, clip_min}
- speed_to_force_poly
  - params: {coeffs: list[float], clip_min: float | None}
- speed_to_eta_poly
  - params: {coeffs: list[float]}

### Converters
- constant_eta
  - params: {eta: float}
- variable_eta
  - params: {eta_default: float, eta_source: str | None}
  - note: eta_default est un fallback si aucun profil eta(t) n'est attache

## Exemple YAML complet
Exemple complet (style storage_dev) :

```yaml
vessel:
  name: "Vevey"
  vessel_type: "DE"

simulation:
  dt: 1.0

profiles:
  - id: "hotel_load"
    kind: "constant"
    unit: "W"
    value: 100000

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
    master: true

adapters:
  - id: "shaft_power_from_speed"
    kind: "speed_to_power_poly"
    source: "speed"
    unit_in: "m/s"
    unit_out: "W"
    params:
      coeffs: [0.0, -209.0, 1904.4, 531.36, 93.312]

  - id: "eta_from_speed"
    kind: "speed_to_eta_poly"
    source: "speed"
    unit_in: "m/s"
    unit_out: "-"
    params:
      coeffs: [0.11138307, 0.03562645, 0.00436722, -0.00056904]

inputs:
  - id: "shaft_demand"
    bus: "Mechanical:shaft"
    source: "shaft_power_from_speed"
    sign: "consume"

  - id: "navops"
    bus: "Electrical:main"
    source: "hotel_load"
    sign: "consume"

solver:
  mode: "inverse"

buses:
  - id: "Mechanical:shaft"
    carrier: "Mechanical"
  - id: "Electrical:main"
    carrier: "Electrical"
  - id: "Chemical:fuel"
    carrier: "Chemical"

converters:
  - id: "motor"
    from_bus: "Electrical:main"
    to_bus: "Mechanical:shaft"
    kind: "constant_eta"
    params:
      eta: 0.9

  - id: "genset"
    from_bus: "Chemical:fuel"
    to_bus: "Electrical:main"
    kind: "variable_eta"
    params:
      eta_default: 0.38
      eta_source: "eta_from_speed"

storages:
  - id: "fuel_tank"
    bus: "Chemical:fuel"
    vecteur: "diesel"
```

## En cours / a valider
- Tester l'hybridation. Cela passera par un management explicite de la puissance.
