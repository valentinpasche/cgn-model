# Guide d’utilisation du modèle en mode script

Ce document explique comment utiliser le modèle CGN en mode script, sans passer
par l’interface graphique. La configuration YAML constitue le point d’entrée
principal du calcul : elle décrit les profils, les transformations, les liaisons
vers le solveur, les bus d’énergie, les convertisseurs et les stockages à
post-traiter.

Le document sert à la fois de guide d’utilisation en mode script et de référence
des champs YAML disponibles.

## Comment utiliser ce document

Pour une premiere prise en main, commencer par
[l'exemple d'utilisation en mode script](example_script.md), qui presente un
calcul complet et directement executable.

Le present document sert ensuite de reference pour comprendre et modifier
chaque section de la configuration YAML.

Pour comprendre la structure du modele et le deroulement interne du calcul,
consulter [Structure et deroulement du calcul](model_workflow.md).

## Vue d'ensemble du modele

- Le solveur (energy_solver) calcule les bilans d'energie sur un DAG (graphe oriente acyclique) de bus + convertisseurs.
- Les profils (profiles) sont des signaux bruts (vitesse, charges, etc.).
- Les adapters transforment ces profils (ex. vitesse -> puissance) et produisent des signaux utilisables par les inputs ou convertisseurs.
- Les inputs lient un signal (profile/adapter) a un bus du solver avec une convention de signe.
- Les convertisseurs (converters) transfèrent l'energie entre bus avec un rendement.
- Les storages (optionnel) permettent de post-traiter un bus comme un stockage (bilan energie/puissance).

Flux d'utilisation principal :

```text
YAML -> Vessel.from_yaml(...) -> Vessel.run() -> Vessel.results_dataframe()
```

Flux interne simplifie :

```text
profiles -> adapters -> inputs -> solver (buses + converters) -> storages/results
```

Note importante :
- Le DAG (buses + converters) doit suivre le sens physique du flux d'energie (from_bus -> to_bus).
- En dehors du DAG, les adapters suivent la convention de nommage (ex. speed_to_power_poly).

Notes de lecture :
- Les termes propres au modele (`profiles`, `adapters`, `inputs`, `buses`,
  `converters`, `storages`, etc.) sont detailles dans les sections YAML
  correspondantes ci-dessous et dans le lexique des modules et classes.
- Un exemple YAML complet est disponible a la fin de ce document.

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

---

### simulation
Parametres globaux.

Champs :
- dt (float, > 0) : pas de temps [s]

Exemple :
```yaml
simulation:
  dt: 1.0
```

---

### profiles
Declaration des profils bruts. Points d'entree temporels du modele.

Champs communs :
- id (str) : identifiant unique
- kind (str) : "constant" | "series" | "file" | "nav_speed"
- unit (str) : unite declaree
- master (bool, optionnel) : profil maitre qui fixe `N`, la longueur temporelle commune des profils

Unites autorisees dans l'UI (profiles, usage general) :
- puissance : "W" | "kW" | "MW" | "GW"
- vitesse : "m/s" | "km/h" | "kn"
- force : "N" | "kN" | "MN" | "GN"

Note :
- `N` designe le nombre de pas de temps du calcul. Les profils `series` et
  `file` doivent avoir `N` valeurs. Les constantes scalaires sont diffusees sur
  `N`; une constante declaree sous forme de liste peut aussi avoir une taille
  `1` ou `N`.
- Le code metier peut accepter davantage d'alias/unites selon les composants.
- Pour l'UI, la liste ci-dessus est volontairement restreinte pour limiter les erreurs utilisateur.

#### kind = constant
Champs :
- value (float | list[float]) : valeur scalaire diffusee sur `N`, ou liste de taille `1` ou `N`

Exemple :
```yaml
- id: "hotel_load"
  kind: "constant"
  unit: "W"
  value: 100000
```

#### kind = series
Champs :
- data (list[float]) : serie explicite de taille N

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
- column (str | null, optionnel) : colonne a lire. Si omis ou `null`, la premiere colonne du CSV est utilisee.
- sep (str | null, optionnel) : separateur CSV (",", ";", "\t", "|"). Defaut `null`, avec auto-detection.
- decimal (str, optionnel) : "." ou ",". Defaut `"."`.
- encoding (str, optionnel) : encodage. Defaut `"utf-8-sig"`.

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
Construit un profil de vitesse a partir des horaires CGN embarques. Ces horaires
sont des CSV internes au code, lus par le module `navigation`.
Si allow_delay = false, le profil doit respecter strictement l'horaire (sinon erreur).

Le profil est genere avec une hypothese MRUA (mouvement rectiligne uniformement
accelere) : acceleration constante au depart, plateau eventuel a la vitesse de
croisiere, puis deceleration constante a l'arrivee. Cette approximation reste
pertinente pour une analyse macro comme celle visee ici.

Champs :
- source (str) : "cgn_croisieres/<name>" (ex. "cgn_croisieres/all"). Le prefixe `cgn_croisieres/` est requis.
- select (dict) : selection par croisiere / course / etape
  - by: "cruise" | "course" | "leg". Alias francais acceptes :
    `"croisiere"`/`"croisière"` et `"etape"`/`"étape"`.
  - cruise_name (str) si by="cruise"
  - course_no (int) si by="course"
  - leg: {from_port: str, to_port: str} si by="leg"
- params (dict, optionnel) : parametres MRUA
  - acc (float, optionnel) : acceleration, defaut `0.04`
  - dec (float, optionnel) : deceleration, defaut `0.04`
  - v_croisiere (float, optionnel) : vitesse de croisiere cible, defaut `7.0`
  - allow_delay (bool, optionnel) : autorise un retard si l'horaire est physiquement impossible, defaut `true`

Contrainte d'unites :
- `unit` du profil `nav_speed` : "m/s" (SI)
- `params.acc` et `params.dec` : en `m/s^2` (SI)
- `params.v_croisiere` : en `m/s` (SI)

Jeux d'horaires disponibles :
- `cgn_croisieres/translemanique`
- `cgn_croisieres/petit_lac_grand_lac`
- `cgn_croisieres/lavaux_haut_lac_grand_lac`
- `cgn_croisieres/lavaux_haut_lac`
- `cgn_croisieres/all` : copie concatenee des quatre jeux ci-dessus

Pour plus de detail sur les CSV et la selection croisiere/course/etape, voir
[navigation_guide.md](navigation_guide.md).

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

---

### adapters
Transformations de profils (ex. vitesse -> puissance).

Champs :
- id (str) : identifiant unique
- kind (str) : type d'adapter, voir les sous-sections ci-dessous
- source (str) : id d'un profile ou d'un adapter (ignore pour multi-entrees)
- unit_in (str) : unite attendue en entree (ignore pour multi-entrees)
- unit_out (str) : unite de sortie
- params (dict) : parametres du kind

Notes :
- Les coefficients empiriques sont fournis par l'utilisateur dans le YAML. Le modele
  applique les formules et conversions declarees, mais ne valide pas la pertinence
  physique des coefficients, leur origine ou leur domaine de validite.
- Les coefficients polynomiaux sont donnes en ordre croissant :
  `a0 + a1*x + a2*x^2 + ...`.
- `unit_in` indique l'unite dans laquelle la variable d'entree est convertie avant
  application des coefficients.
- `unit_out` indique l'unite de sortie declaree pour le signal produit.
- Pour les adapters multi-entrees, `source` et `unit_in` sont ignores par le calcul
  mais doivent etre renseignes pour satisfaire le schema generique.

Ordre des operations dans un adapter mono-entree :

1. lire le signal declare par `source` ;
2. convertir ce signal depuis son unite de profil vers `unit_in` ;
3. appliquer la formule de l'adapter avec les valeurs exprimees dans `unit_in` ;
4. interpreter le resultat dans l'unite native du calcul de l'adapter ;
5. convertir le resultat vers `unit_out`.

Exemple simple :

```yaml
profiles:
  - id: "speed"
    kind: "series"
    unit: "kn"
    data: [10.0]
    master: true

adapters:
  - id: "shaft_power_from_speed"
    kind: "speed_to_power_poly"
    source: "speed"
    unit_in: "m/s"
    unit_out: "kW"
    params:
      coeffs: [0.0, 1000.0]
```

Dans cet exemple, la vitesse `10 kn` est d'abord convertie en `m/s`. Le polynome
est ensuite applique a cette valeur en `m/s`. Le resultat natif est une puissance
en `W`, finalement convertie en `kW`.

#### kind = speed_to_power_poly

Transforme un profil de vitesse en profil de puissance avec un polynome.

Parametres :
- coeffs (list[float]) : coefficients du polynome `P(v)`.
- clip_min (float | null, optionnel) : valeur minimale appliquee a la sortie avant conversion finale.

Interpretation :
- la vitesse source est convertie vers `unit_in` ;
- les coefficients sont appliques a cette vitesse ;
- le resultat du polynome est interprete comme une puissance en W, puis converti vers `unit_out`.

Exemple :
```yaml
- id: "shaft_power_from_speed"
  kind: "speed_to_power_poly"
  source: "speed"
  unit_in: "m/s"
  unit_out: "W"
  params:
    coeffs: [0.0, -209.0, 1904.4, 531.36, 93.312]
```

#### kind = speed_to_force_poly

Transforme un profil de vitesse en profil de force avec un polynome.

Parametres :
- coeffs (list[float]) : coefficients du polynome `F(v)`.
- clip_min (float | null, optionnel) : valeur minimale appliquee a la sortie avant conversion finale.

Interpretation :
- la vitesse source est convertie vers `unit_in` ;
- les coefficients sont appliques a cette vitesse ;
- le resultat du polynome est interprete comme une force en N, puis converti vers `unit_out`.

Exemple :
```yaml
- id: "resistance_from_speed"
  kind: "speed_to_force_poly"
  source: "speed"
  unit_in: "m/s"
  unit_out: "N"
  params:
    coeffs: [-209.0, 1904.4, 531.36, 93.312]
```

#### kind = force_and_speed_to_power

Transforme une force et une vitesse en puissance avec `P = F * v`.

Parametres :
- force_source (str) : id du signal de force.
- speed_source (str) : id du signal de vitesse.
- force_unit_in (str, optionnel) : unite de force utilisee avant calcul, defaut `"N"`.
- speed_unit_in (str, optionnel) : unite de vitesse utilisee avant calcul, defaut `"m/s"`.
- clip_min (float | null, optionnel) : valeur minimale appliquee a la puissance avant conversion finale.

Notes :
- `source` et `unit_in` sont ignores par cet adapter, car les deux sources sont
  declarees dans `params`.
- Ils doivent tout de meme etre presents dans le YAML pour respecter le schema
  commun des adapters. Utiliser par convention `source: ""` et `unit_in: ""`.

Exemple :
```yaml
- id: "shaft_power_from_force_speed"
  kind: "force_and_speed_to_power"
  source: ""
  unit_in: ""
  unit_out: "W"
  params:
    force_source: "resistance_from_speed"
    speed_source: "speed"
    force_unit_in: "N"
    speed_unit_in: "m/s"
```

#### kind = speed_to_eta_poly

Transforme un profil de vitesse en profil de rendement adimensionnel.  
Utilisé pour alimenter un convertisseur à rendement variable.

Parametres :
- coeffs (list[float]) : coefficients du polynome `eta(v)`.

Interpretation :
- la vitesse source est convertie vers `unit_in` ;
- les coefficients sont appliques a cette vitesse ;
- la sortie est adimensionnelle et doit utiliser `unit_out: "-"`.
- lors de l'attachement automatique a un convertisseur `variable_eta`, le profil
  de rendement est borne dans `[1e-6, 1.0]` par defaut afin d'eviter des
  rendements invalides ou nuls.

Exemple :
```yaml
- id: "eta_from_speed"
  kind: "speed_to_eta_poly"
  source: "speed"
  unit_in: "m/s"
  unit_out: "-"
  params:
    coeffs: [0.11138307, 0.03562645, 0.00436722, -0.00056904]
```

#### kind = power_to_power_poly

Transforme un profil de puissance en un autre profil de puissance.

Cet adapter est utile pour appliquer une correction empirique, un changement
d'echelle ou une conversion controlee entre un profil de puissance disponible et
un signal connectable au solveur. Dans l'interface `web_ui_v2`, il sert aussi de
passage par defaut lorsqu'un profil de puissance doit obligatoirement passer par
un adapter avant d'etre connecte au solveur.

Parametres :
- coeffs (list[float]) : coefficients du polynome `P_out(p)`. Dans le YAML, ce
  champ doit etre renseigne. L'interface web utilise souvent `[0.0, 1.0]` comme
  valeur de depart pour un passage direct.
- clip_min (float | null, optionnel) : valeur minimale appliquee a la sortie avant conversion finale.

Interpretation :
- la puissance source est convertie vers `unit_in` ;
- les coefficients sont appliques a cette valeur ;
- le resultat du polynome est interprete comme une puissance en W, puis converti vers `unit_out`.
- pour un simple passage direct, utiliser `unit_in: "W"`, `unit_out: "W"` et
  `coeffs: [0.0, 1.0]`.

Exemple :
```yaml
- id: "hotel_load_adapter"
  kind: "power_to_power_poly"
  source: "hotel_load"
  unit_in: "W"
  unit_out: "W"
  params:
    coeffs: [0.0, 1.0]
```

---

### inputs
Liaison d'un signal (profile/adapter) vers un input du solver.

Champs :
- id (str) : id de l'input (cote solver)
- bus (str) : bus cible (cote solver)
- source (str) : id d'un profile ou d'un adapter
- sign (str) : "consume" | "inject" | "as_is"
- scale (float, optionnel) : facteur multiplicatif

Convention de signe :
- `consume` : une valeur positive de la source devient une demande sur le bus
  (profil negatif dans le solver).
- `inject` : une valeur positive de la source devient une injection sur le bus
  (profil positif dans le solver).
- `as_is` : le signe de la source est conserve.

`scale` est applique avant la politique de signe. Il permet d'ajuster une source
sans creer un nouveau profil : conversion simple de facteur, duplication d'une
charge, correction empirique, etc.

Important : les bus du solver travaillent actuellement en puissance `W`. La
source connectee a un input doit donc etre une puissance en `W` apres passage par
les adapters. Si la source directe est un profil, son unite doit deja etre `W`.

Exemple :
```yaml
- id: "shaft_demand"
  bus: "shaft_bus"
  source: "shaft_power_from_speed"
  sign: "consume"
```

---

### solver
Champs :
- mode (str) : "inverse" | "forward" (forward non valide pour l'instant)

Voir aussi [forward vs inverse](forward_vs_inverse.md) pour une explication
detaillee des deux modes et un exemple numerique.

Exemple :
```yaml
solver:
  mode: "inverse"
```

---

### buses
Declaration des bus du solver.

Un bus est un noeud de bilan de puissance dans le DAG du solveur. Les inputs y
ajoutent une demande ou une injection, et les convertisseurs relient plusieurs
bus entre eux. Un bus n'est donc pas forcement un composant physique detaille :
c'est surtout un point de raccordement et de conservation de puissance.

Champs :
- id (str)
- carrier (str, optionnel) : information descriptive (`Electrical`, `Mechanical`, `Chemical`, etc.)
- unit (str, optionnel) : actuellement forcee a `W` pour les bilans du solveur

Notes :
- `id` est l'identifiant utilise par les inputs et convertisseurs. Il peut etre
  nomme comme un objet metier (`shaft_bus`, `main_electrical_bus`, `fuel_bus`).
- `carrier` est une metadonnee informative. Il est surtout visible dans
  l'affichage brut du DAG.
- Si `carrier` est omis, le solver accepte le bus et utilise quand meme `W`.
- Aujourd'hui, tous les bus du solveur calculent des puissances instantanees en W,
  quel que soit le `carrier`.

Exemple :
```yaml
buses:
  - id: "shaft_bus"
    carrier: "Mechanical"
  - id: "main_electrical_bus"
    carrier: "Electrical"
  - id: "fuel_bus"
    carrier: "Chemical"
```

---

### converters
Convertisseurs du solver (transfert de puissance entre deux bus).

Un convertisseur represente une transformation entre un bus amont (`from_bus`)
et un bus aval (`to_bus`) avec un rendement. Le sens `from_bus -> to_bus` doit
suivre le sens physique du flux d'energie.

Champs :
- id (str)
- from_bus (str)
- to_bus (str)
- kind (str) : "constant_eta" | "variable_eta"
- params (dict) : parametres du kind

#### kind = constant_eta

Rendement constant sur toute la simulation.

Parametres :
- eta (float) : rendement constant, obligatoire.

#### kind = variable_eta

Rendement variable fourni par un profil ou un adapter adimensionnel.

Parametres :
- eta_default (float) : rendement de secours, obligatoire.
- eta_source (str | null, optionnel) : id du profil ou de l'adapter donnant `eta(t)`.

Notes :
- `eta_source` doit produire un signal adimensionnel, generalement avec
  `unit_out: "-"`.
- `eta_default` reste obligatoire meme si `eta_source` est renseigne, car il sert
  de valeur de repli.

Exemple avec les deux kinds :
```yaml
converters:
  - id: "genset"
    from_bus: "fuel_bus"
    to_bus: "main_electrical_bus"
    kind: "constant_eta"
    params:
      eta: 0.38

  - id: "motor"
    from_bus: "main_electrical_bus"
    to_bus: "shaft_bus"
    kind: "variable_eta"
    params:
      eta_default: 0.90
      eta_source: "eta_from_speed"
```

---

### storages (optionnel)
Declaration de bus a post-traiter en stockage.

Un storage n'ajoute pas de dynamique de stockage dans le solveur. Il indique que
le bilan de puissance d'un bus doit etre integre apres calcul pour obtenir une
energie cumulee, puis eventuellement une masse ou un volume selon le vecteur
energetique declare.

Cas d'usage typiques :
- suivre la consommation d'un bus carburant (`fuel_bus`) ;
- exprimer cette energie en litres, kilogrammes ou kWh ;
- ajouter un niveau initial de stockage pour obtenir un niveau restant.

Champs :
- id (str) : identifiant du stockage dans les resultats.
- bus (str) : bus dont le bilan de puissance est integre.
- vector_energy (str | null, optionnel) : nom informatif du vecteur energetique
  (`diesel`, `H2`, `battery`, etc.).
- vector_params (dict | null, optionnel) : parametres de conversion energie ->
  masse/volume.
- initial_level (dict | null, optionnel) : niveau initial du stockage.

#### vector_params

`vector_params` est utile lorsque l'energie integree doit etre convertie en
masse ou en volume.

Champs :
- pci_basis (str) : base du PCI, `"mass"` ou `"volume"`.
- pci_value (float, > 0) : valeur du PCI.
- pci_mass_unit (str, optionnel) : unite du PCI massique, requise si
  `pci_basis: "mass"`.
- pci_volume_unit (str, optionnel) : unite du PCI volumique, requise si
  `pci_basis: "volume"`.
- density_kg_m3 (float, optionnel) : densite, utile pour convertir aussi entre
  masse et volume.

Unites acceptees :
- PCI massique : `"kWh/kg"`, `"MJ/kg"`, `"kJ/kg"`, `"J/kg"`.
- PCI volumique : `"kWh/l"`, `"kWh/m3"`, `"MJ/m3"`, `"kJ/m3"`, `"J/m3"`.

Regles :
- avec `pci_basis: "mass"`, renseigner `pci_mass_unit` et ne pas renseigner
  `pci_volume_unit` ;
- avec `pci_basis: "volume"`, renseigner `pci_volume_unit` et ne pas renseigner
  `pci_mass_unit` ;
- sans `pci_basis`, ne pas renseigner `pci_value`, `pci_mass_unit` ou
  `pci_volume_unit`.

#### initial_level

`initial_level` permet de declarer un niveau de depart. Il est optionnel.

Champs :
- value (float, >= 0) : valeur initiale.
- unit (str) : unite de la valeur initiale.

Unites acceptees :
- energie : `"J"`, `"kJ"`, `"MJ"`, `"Wh"`, `"kWh"`, `"MWh"`.
- masse : `"kg"`, `"t"`.
- volume : `"m3"`, `"l"`.

Regles :
- si `initial_level` est donne en masse ou volume, `vector_params` doit fournir
  un PCI permettant la conversion vers l'energie ;
- la conversion croisee masse <-> volume necessite `density_kg_m3`.

Compatibilite de nommage :
- `vector_energy` est le champ recommande.
- les alias suivants sont acceptes en lecture YAML : `vector_name`, `vector`, `vecteur`.

Exemple (diesel, niveau initial en litres) :
```yaml
storages:
  - id: "fuel_tank"
    bus: "fuel_bus"
    vector_energy: "diesel"
    vector_params:
      pci_basis: "mass"
      pci_value: 11.86
      pci_mass_unit: "kWh/kg"
      density_kg_m3: 840.0
    initial_level:
      value: 1000
      unit: "l"
```

Exemple (base volumique) :
```yaml
storages:
  - id: "h2_tank"
    bus: "h2_bus"
    vector_energy: "h2"
    vector_params:
      pci_basis: "volume"
      pci_value: 3.0
      pci_volume_unit: "kWh/m3"
```

Exemple (stockage electrique, niveau initial en kWh) :
```yaml
storages:
  - id: "battery_pack"
    bus: "battery_bus"
    vector_energy: "battery"
    initial_level:
      value: 32
      unit: "kWh"
```

## Exemple YAML complet

Exemple complet avec stockage sans PCI :

*Pour un exemple avec un stockage détaillé comprenant un PCI, une densité et un
niveau initial, voir [`examples/script_mode_260605`](../examples/script_mode_260605/).*

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
    bus: "shaft_bus"
    source: "shaft_power_from_speed"
    sign: "consume"

  - id: "navops"
    bus: "main_electrical_bus"
    source: "hotel_load"
    sign: "consume"

solver:
  mode: "inverse"

buses:
  - id: "shaft_bus"
    carrier: "Mechanical"
  - id: "main_electrical_bus"
    carrier: "Electrical"
  - id: "fuel_bus"
    carrier: "Chemical"

converters:
  - id: "motor"
    from_bus: "main_electrical_bus"
    to_bus: "shaft_bus"
    kind: "constant_eta"
    params:
      eta: 0.9

  - id: "genset"
    from_bus: "fuel_bus"
    to_bus: "main_electrical_bus"
    kind: "variable_eta"
    params:
      eta_default: 0.38
      eta_source: "eta_from_speed"

storages:
  - id: "fuel_tank"
    bus: "fuel_bus"
    vector_energy: "diesel"
```
