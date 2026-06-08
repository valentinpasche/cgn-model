# Principes de conception du modèle CGN

## Intention générale

Le modèle CGN a été conçu comme un outil de simulation systémique de la chaîne
énergétique d’un bateau. L’objectif n’est pas de reproduire immédiatement un
logiciel de simulation physique complet, mais de disposer d’un outil Python
structuré, exploitable et évolutif, capable de représenter les principaux flux
d’énergie du bateau à différents niveaux de détail.

La logique retenue est volontairement progressive. Le modèle doit pouvoir être
utilisé avec des hypothèses globales lorsque les données disponibles sont
limitées, puis être détaillé lorsque certaines parties de la chaîne énergétique
nécessitent une analyse plus fine. Cette approche permet de produire rapidement
des ordres de grandeur, tout en conservant une structure documentable et
extensible.

Le choix a donc été de privilégier un outil modulaire et traçable, plutôt qu’un
solveur physique généraliste difficile à maintenir. Les composants principaux
sont explicités dans le code et dans la configuration : profils, adaptateurs,
entrées du solveur, bus énergétiques, convertisseurs et stockages.
Ces notions sont également détaillées dans la documentation associée au code,
afin de rendre les responsabilités de chaque composant identifiables.

## Principe de modularité

Le modèle est organisé pour séparer les responsabilités. Chaque partie du code a
un rôle limité :

- les profils décrivent les signaux d’entrée ;
- les adaptateurs transforment ces signaux en grandeurs utilisables ;
- les inputs connectent les signaux au solveur avec une convention de signe ;
- les bus représentent les bilans énergétiques ;
- les convertisseurs représentent les transferts d’énergie entre bus ;
- les stockages post-traitent les bilans cumulés ;
- le `Vessel` assemble ces éléments et prépare la simulation.

Cette séparation évite de concentrer toute la logique dans un seul bloc. Elle
rend le code plus testable, plus traçable et plus simple à faire évoluer. Elle
permet aussi de remplacer une partie du modèle sans modifier toute
l’architecture.

Par exemple, une relation vitesse-puissance peut être représentée par un
polynôme simple dans un premier temps. Si une meilleure donnée devient disponible
plus tard, l’adaptateur correspondant peut être remplacé ou complété sans changer
le fonctionnement général du solveur.

## Configuration par fichiers YAML

La configuration du modèle est portée par des fichiers YAML. Ce choix permet de
décrire un scénario sans modifier le code Python. Le YAML regroupe notamment :

- les métadonnées du bateau ;
- le pas de temps de simulation ;
- les profils d’entrée ;
- les adaptateurs ;
- les inputs du solveur ;
- les bus énergétiques ;
- les convertisseurs ;
- les stockages ;
- le mode de résolution.

Le YAML joue ainsi le rôle de source de vérité pour un scénario donné. Il rend
les cas d’étude plus faciles à relire, à modifier, à versionner, à contrôler et
à comparer.

Un point important est que la configuration reste décrite dans le sens physique
des flux d’énergie. Un convertisseur est déclaré avec un `from_bus` et un
`to_bus`, correspondant au sens réel de conversion. Par exemple, un groupe
électrogène est naturellement décrit comme allant d’un bus chimique vers un bus
électrique.

Cette convention rend le fichier compréhensible pour un utilisateur technique :
le YAML décrit le système physique, pas l’algorithme interne utilisé pour le
résoudre.

## Représentation par graphe énergétique

Le cœur du modèle repose sur un graphe orienté acyclique, ou DAG. Les bus sont
les nœuds du graphe et les convertisseurs sont les liaisons entre ces bus.

Cette représentation a été choisie pour plusieurs raisons :

- elle correspond bien à une chaîne énergétique ;
- elle est visuelle et vérifiable ;
- elle permet de contrôler la cohérence de la configuration ;
- elle impose un ordre de calcul déterministe ;
- elle reste suffisamment simple pour être exploitée sans solveur complexe.

Le graphe est orienté selon le sens physique du flux d’énergie. Le solveur peut
ensuite utiliser ce graphe dans le sens adapté au calcul.

Une représentation visuelle du graphe peut aussi être utilisée comme support de
contrôle ou d'explication, sans modifier le calcul lui-même.

## Mode de calcul inverse

Le mode de calcul principal est le mode inverse. Dans ce mode, on impose une
demande ou un profil d’exploitation, puis le modèle remonte la chaîne énergétique
pour estimer les puissances nécessaires en amont.

Ce mode est adapté au type d’étude visé. En pratique, on dispose souvent d’un
profil de vitesse, d’une demande mécanique ou d’une charge électrique, et l’on
cherche à estimer les besoins correspondants en énergie, en puissance et en
consommation.

Le sens physique des convertisseurs reste inchangé dans la configuration. Le
solveur utilise simplement la méthode inverse de chaque convertisseur pour
remonter les besoins. Cette approche évite de devoir réécrire le YAML selon le
mode de calcul.

Le mode `forward` est prévu dans la structure du code, mais il n’est pas le mode
de référence de la version actuelle. Il est conservé comme possibilité
d’évolution, mais son usage doit être validé sur des cas physiques de référence
avant d’être considéré comme pleinement exploitable.

## Rôle du `Vessel`

Le `Vessel` est l’objet qui fait le lien entre la configuration métier et le
solveur énergétique. Il ne représente pas uniquement le bateau comme entité
physique ; il organise aussi les données nécessaires à la simulation.

Son rôle peut être résumé ainsi :

1. lire et valider la configuration ;
2. construire les profils d’entrée ;
3. construire les adaptateurs ;
4. matérialiser les signaux ;
5. appliquer les conventions de signe ;
6. connecter les inputs au solveur ;
7. préparer le DAG énergétique ;
8. lancer la résolution vectorielle ;
9. post-traiter les stockages ;
10. rassembler les résultats dans un format exploitable.

Ceci permet de garder le solveur relativement générique. Le
solveur ne connaît pas directement les notions de croisière, de bateau ou de
profil de navigation. Il traite des puissances, des bus et des convertisseurs.
Le `Vessel` assure la traduction entre le modèle métier et ce formalisme de
calcul.

L'API utilisateur principale suit cette logique :

```python
from cgn_model import Vessel

vessel = Vessel.from_yaml(yaml_text)
vessel.run()
df = vessel.results_dataframe()
```

Les appels plus détaillés, comme `build_solver()`, `tally_storages()` ou
`run_vector()`, restent disponibles pour l'inspection, le débogage ou les usages
avancés du solveur, mais ils ne sont plus nécessaires dans l'utilisation
standard.

Ce rôle d'orchestration est complété par des modules auxiliaires plus ciblés.
La préparation des profils d'entrée, les liaisons d'inputs, les conventions de
signe et le nommage des résultats sont séparés afin de garder un point d'entrée
unique pour l'utilisateur, tout en conservant des traitements techniques
localisés et faciles à relire.

## Profils et adaptateurs

Les profils représentent les données d’entrée. Ils peuvent être :

- constants ;
- définis par une série de valeurs ;
- lus depuis un fichier CSV ;
- générés à partir des horaires de navigation.

Les adaptateurs permettent ensuite de transformer ces profils en grandeurs
utiles pour le solveur. Par exemple, un profil de vitesse peut être transformé
en puissance arbre, en force de résistance ou en rendement variable.

Cette distinction entre profil et adaptateur est importante. Elle évite de
mélanger les données brutes avec les hypothèses de transformation. Elle permet
aussi d’ajouter de nouvelles relations empiriques ou physiques sans modifier le
format général du modèle.

La convention de signe n’est pas appliquée dans les adaptateurs. Les adaptateurs
produisent des grandeurs physiques. Le signe est appliqué plus tard, au niveau
des inputs du solveur, avec les conventions `consume`, `inject` ou `as_is`.

## Navigation et profils de vitesse

Un module spécifique est dédié à la navigation. Il transforme les horaires CGN en
objets structurés, puis en profils de vitesse utilisables par le modèle
énergétique.

La structure retenue est volontairement simple :

- une `Etape` représente un segment entre deux ports, ou une pause ;
- une `Course` regroupe plusieurs étapes ;
- une `Croisiere` regroupe plusieurs courses et les pauses entre ces courses.

Cette structure suit la logique des données horaires et reste proche de la
réalité d’exploitation. Les pauses internes et les pauses entre courses peuvent
être distinguées, ce qui permet de reconstruire un trajet complet dans l’ordre
chronologique.

Pour générer un profil de vitesse, le modèle utilise une hypothèse MRUA
simplifiée :

- accélération constante ;
- éventuel palier à vitesse de croisière ;
- décélération constante ;
- vitesse nulle pendant les pauses.

Ce choix est un compromis. Il ne cherche pas à représenter finement les
manœuvres portuaires, les effets météo, les courants ou les phases d’accostage.
Il fournit en revanche un profil discret cohérent avec les distances et les
horaires, suffisamment réaliste pour alimenter une étude énergétique globale.

Lorsque les paramètres physiques choisis ne permettent pas de respecter
l’horaire, une logique de retard peut être utilisée. Le retard est alors conservé
et peut être rattrapé sur les pauses selon les paramètres. Cette logique permet
de signaler les incohérences entre contraintes horaires et contraintes physiques,
plutôt que de masquer le problème.

## Stockages

Les stockages sont traités comme un post-traitement des bus du solveur. Un bus
peut être associé à un stockage afin de calculer :

- la puissance signée ;
- les parties positives et négatives ;
- l’énergie cumulée ;
- un niveau de stockage ;
- des conversions éventuelles en masse ou en volume.

Les conversions reposent sur les paramètres du vecteur énergétique, notamment le
PCI et la densité lorsque ces données sont fournies.

Cette approche permet de quantifier les consommations et les bilans sans
introduire immédiatement une boucle dynamique complexe dans le solveur. Elle est
suffisante pour analyser des bilans énergétiques et produire des indicateurs
exploitables.

Des stockages actifs, comme une batterie ou un supercondensateur piloté, peuvent
être ajoutés dans une évolution ultérieure. Dans ce cas, la stratégie la plus
pragmatique consiste d’abord à générer un profil de puissance en amont, puis à le
réinjecter comme input dans le DAG. Un solveur plus complexe ne devient
nécessaire que si l’on veut traiter explicitement des boucles entre stockage,
réseau et groupes de production.

## Validation de la configuration

Une partie importante du modèle concerne la validation des fichiers YAML. Le but
est de détecter les erreurs de configuration le plus tôt possible.

Les validations portent notamment sur :

- la structure des sections YAML ;
- les champs obligatoires ;
- les types de données ;
- les identifiants dupliqués ;
- les références vers des bus ou des signaux inexistants ;
- les cycles dans les dépendances entre profils et adaptateurs ;
- la cohérence des paramètres de stockage.

Cette validation est essentielle pour rendre l’outil fiable et exploitable. Elle évite que
des erreurs de saisie dans un fichier de configuration se traduisent par des
résultats silencieusement faux.

La validation de forme est réalisée avec des schémas Pydantic. Les contrôles
métier complémentaires sont ajoutés dans les modèles de configuration ou dans
les étapes de construction.

## Positionnement par rapport à l’optimisation

Le modèle actuel est d’abord une base de simulation. Il a été conçu pour rester
compatible avec des approches d’optimisation, mais l’optimisation n’est pas
intégrée directement au cœur de la première version.

Cette décision permet de conserver un cœur de calcul stable et maîtrisable. Les
optimisations futures peuvent être branchées en amont du solveur, par exemple
pour générer des profils de consigne :

- puissance d’un stockage ;
- puissance de groupes ;
- stratégie de dispatch ;
- planification sur un horizon temporel.

Ces profils optimisés peuvent ensuite être réinjectés dans le DAG comme des
inputs classiques. Cette approche permet de conserver les mêmes mécanismes de
simulation et les mêmes formats de sortie.

Plusieurs extensions restent possibles :

- contrôleurs locaux ;
- programmation dynamique ;
- optimisation sur graphe temporel ;
- programmation linéaire ou MILP ;
- solveur algébrique par pas ;
- solveur dynamique de type ODE/DAE.

Ces pistes ne sont pas intégrées par défaut, car elles augmenteraient fortement
la complexité de l’outil. Elles restent toutefois compatibles avec la structure
actuelle.

## Limites assumées

Le modèle repose sur des choix simplificateurs. Ces limites sont connues et
assumées :

- le DAG ne traite pas naturellement les boucles énergétiques fortes ;
- les convertisseurs sont principalement statiques ;
- les profils de vitesse restent macroscopiques ;
- les coefficients fournis dans la configuration doivent être accompagnés de
  leur origine et de leur domaine de validité ;
- le mode `forward` doit encore être validé ;
- les stockages actifs nécessitent une stratégie de pilotage ou un solveur plus
  avancé.

Ces limites ne remettent pas en cause l’utilité de l’outil. Elles traduisent le
choix de construire d’abord une base structurée, exploitable et vérifiable,
avant d’ajouter des comportements plus complexes.

## Synthèse des choix principaux

| Sujet | Choix retenu | Justification |
| --- | --- | --- |
| Architecture | Modèle systémique modulaire | Permet de représenter différents niveaux de détail |
| Configuration | YAML | Rend les scénarios lisibles, reproductibles et modifiables sans toucher au code |
| Cœur de calcul | DAG de bus et convertisseurs | Offre une représentation simple, visuelle et déterministe |
| Sens des flux | Sens physique dans le YAML | Garde une configuration lisible et indépendante du mode de calcul |
| Mode de calcul principal | Inverse statique | Adapté aux profils de mission imposés et aux estimations énergétiques |
| Profils | Séparation profiles / adapters / inputs | Distingue données brutes, transformations et connexion au solveur |
| Navigation | Structure Croisiere / Course / Etape | Reste proche des horaires CGN et de l’exploitation réelle |
| Vitesse | Profil MRUA discret | Compromis entre simplicité, cohérence horaire et exploitabilité énergétique |
| Stockages | Post-traitement des bus | Permet de calculer les bilans sans complexifier le solveur |
| Optimisation | Extension future en amont du solveur | Conserve un cœur stable tout en permettant des stratégies avancées |

## Conclusion

Le modèle CGN a été conçu autour d’un principe directeur : fournir un outil
technique structuré, exploitable et évolutif pour analyser les flux
macroscopiques dans une chaîne énergétique.

La structure retenue repose sur une configuration YAML, un objet `Vessel`
orchestrateur, un solveur DAG de bus et convertisseurs, et des modules dédiés aux
profils, aux signaux, à la navigation, aux résultats et aux stockages. Cette
architecture permet de produire des résultats utiles tout en restant traçable,
contrôlable et réutilisable.

Les choix effectués privilégient la traçabilité, la modularité et l’incrémentalité.
Les évolutions plus avancées, comme les stockages actifs, les stratégies
d’optimisation ou les solveurs dynamiques, restent possibles, mais ne sont pas
imposées au cœur actuel du modèle.
