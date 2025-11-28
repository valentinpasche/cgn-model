# CGN – Plan d’évolution du modèle de simulation

Super notes — tu vas dans la bonne direction. Voilà comment je structurerais la suite, point par point, avec des choix “maintenables” et un plan d’implémentation par étapes.

---

## Recos rapides (TL;DR)

- **Units** : ajoute tout de suite des **métadonnées d’unités** (strings + “carrier” → 1 unité canonique par carrier) et des **asserts de compatibilité**. Décale l’intégration `pint` à plus tard (phase 2), quand les blocs seront stables.
- **Inputs & Stockages** : garde **le DAG pour les conversions stateless**. Modélise le **stockage comme un acteur stateful** piloté en “stepper” (dt), attaché à un bus, **pas** comme une arête de conversion (sinon cycles). Affiche-le dans le **DAG de vue** comme un nœud spécial (comme les inputs).
- **Vitesse → Puissance** : fais un **adapter hors-DAG** (dans `Vessel`) qui convertit “profil de vitesse” → “profil de puissance arbre”. Le DAG reste **mono-domaine puissance** (W). Tu gardes la clarté et évites des conversions unitaires dans le graphe.
- **Statique vs temporel** : garde le moteur **vectoriel** pour les cas simples; ajoute un **stepper** (boucle sur t) dès que tu touches au stockage et aux limites.
- **Limites & priorités** : ajoute des **params génériques** (p_in_max/p_out_max, ramp, etc.) dans `ConverterParams`. En “inverse” et “forward”, **sature** le débit, expose des **KPIs : unmet_demand / spilled_energy**, et des **heures de fonctionnement** (on/off) par composant.

---

## 1) Unités dans le contrat

### Phase 1 (maintenant)
- Ajoute une **unité canonique** par `Bus` (ex: `Electrical: W`, `Mechanical: W`, `Chemical: W_LHV` si tu veux déjà distinguer).  
- Dans `Cfg.BusCfg` : `unit: StrictStr`.  
- Dans `Bus(dataclass)` : `unit: str`.  
- À la construction, **assert** que tous les convertisseurs **conservent l’unité de leur bus amont/aval** (ici W↔W).  
- Dans `Vessel`, fais les conversions “exotiques” (km/h → W, kWh → W via dt) **avant** de créer les inputs du solveur.

### Phase 2 (plus tard)
- Remplace `unit: str` par `Quantity` `pint` **uniquement aux frontières** (I/O, reporting). Le cœur du solveur reste en **float64 SI** (W, s), c’est plus rapide et simple.

---

## 2) Inputs & Stockages : dans le DAG ou à côté ?

- **DAG exécution** : conserve uniquement des **conversions stateless** `u→v`.  
- **Inputs** : restent **exogènes**, affichés en pointillé (comme aujourd’hui).  
- **Stockages** : objets **stateful** avec `soc`, `capacity`, `p_charge_max`, `p_discharge_max`, `eta_c`, `eta_d`, `leakage`.  
  - Exécution : **stepper** (dt) → mise à jour `soc(t+dt)`.  
  - Affichage : ajoute un nœud “battery:main” relié en pointillé à `Electrical:main` (vue), **mais sans arête exécutable** pour éviter un cycle dans le DAG.

---

## 3) Ouvrir le DAG au-delà de W ?

Je ne le ferais **pas** tout de suite.  
Ton besoin vitesse→puissance est un **adapter** (physique navale) : `P_shaft = f(vitesse)` (polynomiale, lookup, modèle). Place-le dans `Vessel` → il **produit un profil W** pour l’`input` “shaft_demand”. Le DAG reste **énergétique** en W et gagne en lisibilité.

---

## 4) Temporel, intégration & reporting

- Ajoute un **stepper** :
  1. Appliquer inputs à t (profils W) → `net_w` des bus.  
  2. **Politique “inverse”** : couvrir les déficits (discharge storage en priorité si tu veux) → `genset`, etc.  
  3. **Politique “forward”** : si surplus, charger le stockage (capé par `p_charge_max`).  
  4. **Saturations** des convertisseurs (limites) → résidu “unmet_demand” ou “spilled_energy”.  
  5. Mise à jour **SoC** et **compteurs** (énergie consommée, heures ON, etc.).  
- Reporting fin de simu :  
  - Consommations par vecteur (volume/masse → fais la conversion dans `Vessel`, pas dans le solver).  
  - Heures de fonctionnement (= somme des pas où `p_in > 0` au-dessus d’un seuil).  
  - Heures ravitaillement = `énergie à charger / débit`.  
  - **Comparaison d’architectures** : même profils/“course”, YAML différent → mêmes métriques consolidées.

---

## 5) Limites des composants & correction des inputs

- Ajoute dans `ConverterParams` des champs **optionnels** :
  - `p_in_max: float | None`, `p_out_max: float | None`  
  - `ramp_up: float | None` (W/s), `ramp_down: float | None` (optionnel, steppper only)  
  - (stockage aura ses propres params)  
- **Inverse** : `p_out_target = need_v`; clamp :  
  `p_out = min(p_out_target, p_out_max)` et `p_in = min(inverse(p_out), p_in_max)` → recalcule `p_out = forward(p_in)` si besoin.  
  Résidu = `need_v - p_out`.  
- **Forward** : comme déjà fait, mais clamp avec `p_in_max/p_out_max`.
- L’**automatisation** de la correction d’inputs (suivre un profil vitesse malgré limites) passera par une **politique** :  
  - priorité stockage, puis genset, etc.  
  - ou optimisation (LP/QP) plus tard.

---

## Ébauche de schéma YAML (extensions)

```yaml
vessel:
  name: "Vevey"
  vessel_type: "DE"   # "steam" | "DE" | "undefined"

profiles:
  course_id: 12
  speed_profile:   # [kn] ou [m/s] — converti en W dans Vessel
    unit: "kn"
    data: [10, 12, 15, 12, 8, ...]
  navops_profile:
    unit: "W"
    data: [8000, 8200, 7500, ...]

solver:
  mode: "inverse"

buses:
  - id: "Mechanical:shaft"
    carrier: "Mechanical"
    unit: "W"
  - id: "Electrical:main"
    carrier: "Electrical"
    unit: "W"
  - id: "Chemical:fuel"
    carrier: "Chemical"
    unit: "W"     # côté solver = puissance équivalente (LHV)

inputs:
  - { id: "shaft_demand", bus: "Mechanical:shaft" }
  - { id: "navops",       bus: "Electrical:main" }

converters:
  - id: "genset"
    from_bus: "Chemical:fuel"
    to_bus:   "Electrical:main"
    kind: "constant_eta"
    params:
      eta: 0.45
      p_out_max: 1.2e6      # W
  - id: "motor"
    from_bus: "Electrical:main"
    to_bus:   "Mechanical:shaft"
    kind: "constant_eta"
    params:
      eta: 0.9
      p_out_max: 1.0e6

storage:
  - id: "battery_main"
    bus: "Electrical:main"
    capacity: 2.0e9       # J (ou Wh si tu préfères, mais convertis en J en interne)
    soc_init: 1.0e9       # J
    p_charge_max: 5.0e5   # W
    p_discharge_max: 5.0e5
    eta_c: 0.96
    eta_d: 0.96
    leakage: 0.0          # J/s
```

> `storage` reste **hors `converters`** → pas d’arêtes exécutables, pas de cycles. Affiche-le dans `view` en pointillé.

---

## Changements concrets à coder (petites étapes)

1) **Units**  
   - `BusCfg.unit: StrictStr` → `Bus.unit: str`.  
   - Assert côté solver : tous les convertisseurs que tu as **aujourd’hui** restent W→W (trivial).  
2) **Limites génériques**  
   - Dans `ConverterParams` du registre : supporte `p_in_max` / `p_out_max`.  
   - Dans `run_vector` : clamp dans les deux branches. Expose `unmet_demand` / `spilled`.  
3) **Stockage (stepper)**  
   - Nouvelle classe `Storage` (Pydantic cfg + dataclass state).  
   - Stepper `run_stepper(dt)` : ordre simple par politique (storage d’abord ou après, selon besoin), mise à jour SoC, heures ON, bilans.  
   - Affichage : nœud en pointillé dans `view`.  
4) **Adapter vitesse→puissance**  
   - Dans `Vessel`, calcule `shaft_demand` (W) depuis `speed_profile` + polynôme/lookup, **avant** d’appeler le solveur.  
5) **Reporting**  
   - Fonctions utilitaires : `energy_integral(W, dt) -> J`, `J_to_liters(vector_props)`, temps de ravitaillement = `E_charge / débit`.  
   - Heures de fonctionnement = `sum(p>seuil)*dt`.
