# Guide du module navigation

Le module `cgn_model.navigation` transforme des horaires de navigation en objets
Python structurés, puis en profils temporels de vitesse.

Il peut être utilisé de deux manières :

- directement, pour inspecter des horaires, vérifier leur continuité et générer
  des profils de vitesse indépendamment du modèle énergétique ;
- depuis une configuration YAML avec un profil `kind: nav_speed`.

La configuration YAML complète de `nav_speed` est documentée dans le
[guide d'utilisation en mode script](script_guide.md). Le présent document se
concentre sur les données horaires et leur interprétation par le module
navigation.

## Objets de navigation

Les horaires sont convertis en trois niveaux d'objets :

- `Etape` : déplacement entre deux ports, ou pause ;
- `Course` : suite ordonnée d'étapes associées au même numéro de course ;
- `Croisiere` : ensemble ordonné de courses et de pauses entre ces courses.

Ces objets permettent notamment d'inspecter :

- les ports de départ et d'arrivée ;
- les distances et durées totales ;
- les temps de navigation et de pause ;
- la vitesse moyenne ;
- la continuité du trajet ;
- le profil de vitesse généré.

## Données CSV embarquées

Les CSV embarqués avec le package se trouvent dans :

```text
src/cgn_model/navigation/data/cgn_croisieres/
```

Jeux d'horaires disponibles :

- `translemanique.csv`
- `petit_lac_grand_lac.csv`
- `lavaux_haut_lac_grand_lac.csv`
- `lavaux_haut_lac.csv`
- `all.csv`, copie concaténée des quatre jeux précédents

Pour charger un fichier embarqué, son nom est fourni sans extension :

```python
from cgn_model.navigation import Croisiere

croisieres = Croisiere.from_cgn_croisiere_csv("all")
```

## Structure d'un CSV

Les fichiers utilisent le séparateur `;` et contiennent les colonnes suivantes :

| Colonne | Type attendu | Rôle |
| --- | --- | --- |
| `croisiere` | texte | nom de la croisière |
| `course` | entier | numéro de course |
| `port` | texte | port correspondant à la ligne |
| `horaire` | texte `HHhMM` | heure de départ depuis ce port |
| `km` | nombre | distance vers le port de la ligne suivante |
| `minutes` | nombre | durée vers le port de la ligne suivante |

Une ligne décrit donc le départ d'un segment. La destination est donnée par le
port de la ligne suivante. La dernière ligne d'une croisière ferme le dernier
segment et ne crée pas elle-même une nouvelle étape.

Les valeurs vides de `croisiere` et `course` sont propagées depuis les lignes
précédentes.

## Exemple d'interprétation d'un CSV

L'exemple fictif suivant contient deux croisières, trois courses et une pause
entre deux courses :

| croisiere | course | port | horaire | km | minutes |
| --- | ---: | --- | --- | ---: | ---: |
| Démonstration matin | 101 | Lausanne | 08h00 | 5 | 15 |
|  |  | Pully | 08h15 | 3 | 10 |
|  |  | Lutry | 08h25 | 0 | 5 |
|  |  | Lutry | 08h30 | 4 | 15 |
|  |  | Cully | 08h45 | 0 | 10 |
|  | 102 | Cully | 08h55 | 6 | 20 |
|  |  | Vevey | 09h15 |  |  |
| Démonstration soir | 201 | Vevey | 18h00 | 8 | 25 |
|  |  | Montreux | 18h25 | 1 | 10 |
|  |  | Château de Chillon | 18h35 |  |  |

Le module interprète cet exemple ainsi :

1. Les cellules vides héritent de la dernière croisière et de la dernière course
   renseignées.
2. `Lausanne -> Pully` et `Pully -> Lutry` deviennent deux `Etape` de la course
   `101`.
3. La ligne `Lutry`, avec `km = 0` et sans changement de course, devient une
   pause interne à la course `101`.
4. `Lutry -> Cully` devient une étape de navigation de la course `101`.
5. La ligne `Cully`, avec `km = 0` juste avant le passage de la course `101` à
   la course `102`, devient une pause entre les deux courses.
6. `Cully -> Vevey` devient une étape de la course `102`.
7. La seconde croisière crée séparément la course `201`, composée des étapes
   `Vevey -> Montreux` et `Montreux -> Château de Chillon`.

Les pauses internes restent dans leur `Course`. Les pauses associées à un
changement de numéro de course sont conservées séparément dans la `Croisiere`,
puis replacées dans l'ordre chronologique par sa propriété `trajet`.

## Utilisation directe du module

L'utilisation directe est utile pour inspecter les horaires avant de choisir une
croisière, une course ou une étape particulière pour le modèle énergétique.

### Charger et afficher les horaires

```python
from cgn_model.navigation import Croisiere

# CSV embarqué dans le package.
croisieres = Croisiere.from_cgn_croisiere_csv("all")

# Affichage lisible de toutes les croisières, courses et étapes.
Croisiere.view_croisiere(croisieres)
```

Quelques propriétés utiles :

```python
croisiere = croisieres[0]

print(croisiere.nom)
print(croisiere.total_km)
print(croisiere.total_minutes)
print(croisiere.nav_minutes)
print(croisiere.pause_minutes)
print(croisiere.avg_speed_kmh)
print(croisiere.check_continuite())
```

### Générer un profil de vitesse

```python
from cgn_model.navigation import Croisiere, SpeedProfileParams

croisieres = Croisiere.from_cgn_croisiere_csv("all")
croisiere = croisieres[0]

params = SpeedProfileParams(
    dt=1.0,
    acc=0.04,
    dec=0.04,
    v_croisiere=7.0,
    allow_delay=True,
)

profile, remaining_delay = croisiere.speed_profile(params)
```

La méthode `speed_profile()` est également disponible sur une `Course` ou une
`Etape`, ce qui permet d'étudier uniquement une partie du trajet.

## Paramètres de génération du profil

`SpeedProfileParams` configure le profil MRUA utilisé par le module navigation.

| Paramètre | Valeur par défaut | Rôle |
| --- | ---: | --- |
| `dt` | `1.0 s` | pas de discrétisation temporelle |
| `acc` | `0.04 m/s²` | accélération constante au départ |
| `dec` | `0.04 m/s²` | décélération constante à l'arrivée |
| `v_croisiere` | `7.0 m/s` | vitesse cible et maximum du plateau de croisière |
| `v_moyenne_horaire` | `None` | vitesse moyenne de référence optionnelle |
| `allow_delay` | `True` | autorise un retard si l'horaire est physiquement impossible |

Le profil généré utilise une approximation MRUA :

1. accélération constante ;
2. plateau éventuel à `v_croisiere` ;
3. décélération constante ;
4. vitesse nulle pendant les temps d'attente et les pauses.

Si la distance est trop courte pour atteindre `v_croisiere`, le profil est
triangulaire : la vitesse augmente puis diminue sans plateau.

Cette représentation ne cherche pas à reproduire finement les manœuvres ou les
conditions extérieures. Elle fournit un profil cohérent avec les distances,
horaires et contraintes de vitesse, adapté à une analyse énergétique
macroscopique.

### Principe de `allow_delay`

Pour chaque étape, le module compare :

- la durée disponible dans l'horaire ;
- la durée physique minimale nécessaire avec les valeurs choisies pour
  `acc`, `dec` et `v_croisiere`.

Lorsque l'étape est réalisable dans le temps prévu, le temps disponible en plus
est représenté par des périodes à vitesse nulle avant et après la navigation.

Lorsque l'horaire est physiquement impossible :

- avec `allow_delay=False`, la génération s'arrête avec une erreur ;
- avec `allow_delay=True`, le profil physique est conservé et le retard est
  enregistré.

Le retard peut ensuite être partiellement ou totalement récupéré sur les temps
d'attente et les pauses suivants. S'il ne peut pas être entièrement récupéré,
il est propagé jusqu'à la fin de la course ou de la croisière.

Ce mécanisme évite de créer artificiellement un profil incompatible avec les
contraintes physiques uniquement pour respecter l'horaire. Il permet aussi
d'identifier les étapes critiques et d'évaluer si les hypothèses de vitesse et
d'accélération sont cohérentes avec l'exploitation prévue.

`v_moyenne_horaire` constitue un contrôle macro complémentaire. Lorsqu'elle est
renseignée, un avertissement est émis si la vitesse moyenne effective s'écarte
fortement de cette référence.

## Utilisation depuis le YAML

Dans une configuration du modèle énergétique, `kind: nav_speed` charge les
horaires, sélectionne un objet de navigation et génère son profil de vitesse.

Exemple minimal :

```yaml
- id: "speed"
  kind: "nav_speed"
  unit: "m/s"
  source: "cgn_croisieres/all"
  select:
    by: "croisiere"
    cruise_name: "Lavaux - Haut-Lac"
  params:
    acc: 0.05
    dec: 0.05
    v_croisiere: 7.0
    allow_delay: true
```

Sélections disponibles :

- `cruise`, `croisiere` ou `croisière`, avec `cruise_name` ;
- `course`, avec `course_no` ;
- `leg`, `etape` ou `étape`, avec
  `leg: {from_port: <str>, to_port: <str>}`.

Dans le YAML, `simulation.dt` remplace le `dt` de `SpeedProfileParams`. Le champ
`v_moyenne_horaire` est disponible lors de l'utilisation directe du module, mais
n'est actuellement pas exposé dans les paramètres YAML de `nav_speed`.

Pour la référence complète des champs YAML, consulter le
[guide d'utilisation en mode script](script_guide.md).

## Ajouter un nouveau CSV

Pour ajouter un jeu d'horaires embarqué :

1. créer un fichier `<name>.csv` dans
   `src/cgn_model/navigation/data/cgn_croisieres/` ;
2. utiliser le séparateur `;` et les colonnes documentées plus haut ;
3. vérifier que chaque ligne décrit correctement le segment vers la ligne
   suivante ;
4. laisser vides les cellules `croisiere` et `course` uniquement lorsqu'elles
   doivent hériter de la valeur précédente ;
5. utiliser `km = 0` pour représenter une pause ;
6. charger et contrôler le fichier avant de l'utiliser dans un calcul.

```python
from cgn_model.navigation import Croisiere

croisieres = Croisiere.from_cgn_croisiere_csv("<name>")

for croisiere in croisieres:
    assert croisiere.check_continuite()
    Croisiere.view_croisiere(croisiere)
```

Pour inspecter un CSV local sans l'ajouter au package :

```python
croisieres = Croisiere.from_csv("mon_fichier.csv")
```

Le nom `<name>` devient ensuite utilisable dans le YAML avec :

```yaml
source: "cgn_croisieres/<name>"
```
