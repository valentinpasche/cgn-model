# Synthese du processus et des choix de developpement

## Objectif du document

Ce document synthetise le cheminement de conception de l'outil CGN-model et les
principaux choix effectues pendant son developpement. Il ne remplace pas la
documentation metier du code ; il sert plutot a expliquer pourquoi l'outil a pris
cette forme et quelles contraintes ont guide les decisions techniques.

Pour la definition statique des modules, classes et objets du package, voir
`lexique_modules_classes.md`.

La synthese s'appuie sur les trois exports de discussions conserves dans
`temp_doc` :

- `ChatGPT-1) Point de depart - Architecture.md`
- `ChatGPT-2) Finalisation SolverDAG, Vessel.md`
- `ChatGPT-3) Navigation.md`

## Besoin initial

Le besoin de depart etait de construire un modele de simulation de la chaine
energetique d'un bateau, en Python, avec une structure suffisamment generale pour
etre detaillee progressivement. L'outil devait permettre de partir d'un modele
global, puis de remplacer certains blocs par des sous-systemes plus fins lorsque
les donnees ou le niveau d'analyse le justifient.

Cette logique correspond a une approche systemique :

- commencer avec des blocs agreges donnant des ordres de grandeur ;
- garder des interfaces stables entre les blocs ;
- raffiner uniquement les parties utiles a l'etude ;
- conserver une structure lisible pour un utilisateur technique, pas seulement
  pour un developpeur.

L'inspiration initiale venait d'outils de simulation systeme de type Amesim :
des composants connectes par des entrees/sorties, avec des grandeurs physiques et
des unites explicites. Le choix final n'a toutefois pas ete de reproduire un
solveur acausal complet, mais de construire une architecture Python pragmatique,
plus simple, adaptee aux donnees disponibles et aux objectifs de l'etude.

## Principes de conception retenus

### Modularite progressive

Le modele a ete pense pour permettre plusieurs niveaux de detail. Un bloc peut
d'abord representer une chaine complete avec un rendement global, puis etre
remplace par plusieurs composants plus detailles.

Ce principe a conduit a privilegier :

- des objets metier simples ;
- des interfaces explicites ;
- une configuration externe en YAML ;
- une separation entre le modele physique, les donnees d'entree et le solveur.

L'objectif est que l'utilisateur puisse comprendre la structure generale avant
d'entrer dans le detail de chaque equation ou coefficient.

### Composition plutot qu'heritage complexe

La conception s'est orientee vers des objets composes entre eux, plutot qu'une
grande hierarchie de classes. Les discussions initiales mentionnaient les
concepts de `Component`, `Port`, `Signal`, `Composite`, `Protocol` et
`dataclass`. Dans l'implementation actuelle, cette idee a ete simplifiee autour
de blocs directement utiles au projet :

- des profils d'entree ;
- des adapters ;
- des inputs signes ;
- des bus energetiques ;
- des convertisseurs ;
- des stockages ;
- un objet `Vessel` qui assemble l'ensemble.

Ce choix rend le code plus accessible et evite une architecture trop abstraite
pour un premier outil exploitable.

### Configuration YAML comme source de verite

Le YAML a ete retenu comme support central de configuration. Il permet de decrire
un scenario sans modifier le code Python :

- type et nom du bateau ;
- pas de temps ;
- profils d'entree ;
- transformations de profils ;
- inputs connectes aux bus ;
- bus energetiques ;
- convertisseurs ;
- stockages ;
- mode de resolution.

Ce choix repond a deux objectifs :

- rendre les scenarios reproductibles et versionnables ;
- permettre a un utilisateur de verifier la logique du modele a partir d'un
  fichier lisible.

Le YAML est volontairement garde dans un sens physique. Par exemple, un
convertisseur est defini par `from_bus -> to_bus` selon le sens reel du flux
d'energie. Le solveur peut ensuite exploiter cette information dans un mode
inverse ou, a terme, dans un autre mode, sans que la configuration soit reecrite.

### Graphe physique et solveur DAG

Une decision structurante a ete de representer la chaine energetique sous forme
de graphe oriente acyclique, ou DAG.

Le graphe d'execution est construit autour de bus et de convertisseurs :

- les bus representent des niveaux ou noeuds energetiques ;
- les convertisseurs representent les transferts entre bus ;
- les aretes suivent le sens physique de l'energie ;
- le solveur utilise l'ordre topologique du graphe pour propager les besoins ou
  les flux.

Ce choix a plusieurs avantages :

- il est lisible visuellement ;
- il correspond bien a une chaine d'energie sans boucle forte ;
- il permet de controler la coherence du YAML ;
- il produit rapidement des ordres de grandeur ;
- il reste compatible avec des evolutions futures.

Le DAG a ete choisi comme solution initiale parce qu'il est robuste, simple a
comprendre et suffisant pour les cas de conversion energetique instantanee
traites au depart. Des solveurs plus generaux, comme des solveurs ODE/DAE ou des
optimisations temporelles, ont ete discutes mais volontairement repousses.

### Separation entre graphe d'execution et graphe de visualisation

Un point important du processus a ete la distinction entre :

- le graphe utilise pour calculer ;
- le graphe utilise pour afficher et documenter.

Les inputs peuvent etre utiles dans une vue graphique, car ils montrent comment
les profils sont connectes aux bus. Mais ils ne doivent pas perturber le tri
topologique ni la resolution du DAG.

Le choix retenu est donc de conserver :

- un graphe d'execution, limite aux bus et convertisseurs ;
- un graphe de visualisation, enrichi avec des noeuds virtuels pour les inputs.

Cette separation permet d'avoir un calcul propre tout en gardant un support de
controle et de communication comprehensible.

### Mode inverse comme premier cas d'usage

Le premier usage vise est essentiellement inverse : a partir d'un profil de
vitesse, d'une demande mecanique ou d'une charge electrique, l'outil remonte la
chaine energetique pour estimer les puissances amont et la consommation.

Dans cette logique :

- le YAML reste physique ;
- les convertisseurs portent idealement une methode directe et une methode
  inverse ;
- le solveur choisit le sens de parcours ;
- les inputs representent des demandes ou injections signees.

Ce choix est adapte a une etude d'ordre de grandeur : on impose une mission ou
un profil d'exploitation, puis on estime les besoins energetiques correspondants.

Le mode `forward` a ete identifie comme une evolution possible, mais le mode
inverse est le mode de reference pour les exemples documentes.

## Role du Vessel

L'objet `Vessel` joue le role d'assembleur entre la configuration et le solveur.
Il ne se limite pas a representer un bateau au sens physique ; il organise aussi
les donnees necessaires a la simulation.

Son role conceptuel est le suivant :

1. charger la configuration ;
2. construire les profils ;
3. appliquer les adapters ;
4. materialiser les signaux ;
5. appliquer les conventions de signe ;
6. connecter les inputs au solver ;
7. construire le DAG energetique ;
8. lancer la resolution ;
9. post-traiter les stockages ;
10. produire des resultats sous forme exploitable.

Ce decoupage a ete retenu pour eviter que le solveur ne connaisse directement
toute la logique metier du bateau. Le solveur traite des bus, des convertisseurs
et des profils signes ; le `Vessel` fait le lien avec la configuration et les
objets metier.

L'organisation recente renforce cette intention. `Vessel` reste le point
d'entree principal, mais les traitements auxiliaires sont davantage localises :
`profiles.py` prepare les profils d'entree, `signals.py` regroupe les bindings
et les politiques de signe, et `results_utils.py` regroupe les conventions de
nommage des resultats. Le role public de `Vessel` ne change pas, mais son code
devient plus proche d'un orchestrateur que d'un module contenant tous les
details.

Cette intention se traduit aussi dans l'API publique. L'usage metier principal
est maintenant :

```python
from cgn_model import Vessel

vessel = Vessel.from_yaml(yaml_text)
vessel.run()
df = vessel.results_dataframe()
```

La methode `run()` regroupe la preparation du solver, l'appel a `run_vector` et
le post-traitement des stockages. Les methodes plus fines restent accessibles
pour les usages avances, mais l'utilisateur courant n'a plus besoin de manipuler
directement `vessel.solver`.

## Choix autour des profils et adapters

Les profils representent les signaux bruts ou exogenes :

- constantes ;
- series explicites ;
- fichiers CSV ;
- profils de vitesse issus de la navigation.

Les adapters transforment ces profils en grandeurs utilisables par le solver,
par exemple :

- vitesse vers puissance ;
- vitesse vers force ;
- force et vitesse vers puissance ;
- vitesse vers rendement.

Ce choix a ete fait pour garder une separation claire entre :

- les donnees d'entree ;
- les transformations physiques ou empiriques ;
- les inputs effectivement connectes au solveur.

Cela permet aussi d'ajouter de nouveaux types de transformations sans changer la
structure generale du solver.

## Choix autour de la navigation

Un module de navigation a ete ajoute pour transformer les donnees horaires CGN en
profils exploitables par le modele energetique.

La conception est partie d'un CSV d'horaires contenant :

- le nom de la croisiere ;
- le numero de course ;
- les ports ;
- les horaires ;
- les distances ;
- les durees.

Le choix initial a ete de construire une structure objet simple :

- `Etape` pour un segment entre deux ports, ou une pause ;
- `Course` pour une sequence d'etapes ;
- `Croisiere` pour une sequence de courses et de pauses.

Les pauses internes et les pauses entre courses ont ete distinguees afin de
conserver une representation proche de l'exploitation reelle. Une propriete de
type `trajet` a ete introduite pour parcourir chronologiquement les courses et
les pauses sans dupliquer les objets.

### Profil de vitesse

Pour alimenter le solver energetique, les horaires doivent etre convertis en
profils de vitesse. Le choix retenu est un profil MRUA simplifie :

- acceleration constante ;
- eventuel plateau a vitesse de croisiere ;
- deceleration constante ;
- profil nul pour les pauses.

Ce modele est volontairement macroscopique. Il ne cherche pas a representer en
detail les manoeuvres portuaires, les effets de courant, les conditions meteo ou
les phases fines d'accostage. Il donne en revanche un profil discret coherent
avec les distances et les horaires, utilisable pour calculer une puissance.

La gestion du retard a ete introduite comme garde-fou lorsque les contraintes
physiques choisies ne permettent pas de respecter exactement l'horaire. Le retard
peut etre conserve, propage puis eventuellement rattrape sur des pauses selon les
parametres.

## Choix autour des stockages

Les stockages ont ete abordes comme un post-traitement ou comme un futur point
d'evolution du modele.

Dans l'approche actuelle, un stockage peut etre rattache a un bus pour suivre un
bilan d'energie cumulee et, si les parametres sont fournis, convertir cette
energie en masse ou volume via un PCI et une densite.

Ce choix permet de documenter et quantifier les consommations sans introduire
immediatement de boucle dynamique forte dans le solver.

Pour des stockages actifs, par exemple une batterie ou un supercondensateur qui
charge et decharge selon une strategie, deux evolutions ont ete discutees :

- generer un profil de puissance en amont, via un adapter ou un controleur
  "offline", puis le reinjecter comme input dans le DAG ;
- ajouter plus tard un stepper algebrique ou un solveur plus general pour traiter
  les boucles stockage-reseau-groupe.

La recommandation de conception a ete de commencer par l'approche la plus simple,
compatible avec le pipeline existant, puis de n'ajouter un solveur plus complexe
que lorsque le besoin est confirme.

## Choix de validation et qualite logicielle

Le developpement a progressivement fait apparaitre le besoin de separer :

- parsing de la configuration ;
- validation de schema ;
- controles metier ;
- construction des objets ;
- construction des graphes ;
- execution ;
- export des resultats.

Cette separation a ete recommandee pour eviter qu'une methode comme `from_yaml`
devienne un bloc trop long et difficile a tester.

Le recours a des structures type `dataclass`, a des interfaces legeres et a une
validation de configuration a ete privilegie pour rendre le code :

- lisible ;
- testable ;
- extensible ;
- moins sujet aux erreurs silencieuses.

Les discussions ont aussi identifie l'interet de bibliotheques de validation
comme Pydantic ou jsonschema pour verifier les configurations YAML. L'idee est de
laisser la validation de forme au schema, puis de reserver les controles metier
aux contraintes croisees : identifiants uniques, references vers des bus
existants, bornes de rendement, coherence des unites, etc.

## Positionnement par rapport a l'optimisation

Le projet a ete pense comme une base de simulation exploitable, avec une ouverture
vers l'optimisation, mais l'optimisation n'a pas ete placee au coeur de la
premiere architecture.

Plusieurs pistes ont ete discutees :

- controle local ou politique de dispatch ;
- programmation dynamique sur un DAG temporel ;
- reseau temps-etendu avec flot ou programmation lineaire ;
- MILP pour des decisions on/off ;
- solveur algebrique par pas ;
- ODE/DAE ou approche proche Amesim pour des sous-modeles dynamiques.

Le choix pragmatique retenu est de garder le DAG instantane comme coeur physique
et de brancher d'eventuels controleurs ou optimiseurs en amont. Ces modules
produiraient alors des profils de consigne reinjectes dans le solver existant.

Cette strategie limite les risques :

- le coeur actuel reste stable ;
- les scenarios simples restent faciles a comprendre ;
- l'optimisation peut etre ajoutee progressivement ;
- les sorties restent comparables entre approches.

## Limites assumees

Plusieurs limites ont ete volontairement acceptees pour conserver un outil
exploitable :

- le DAG ne traite pas naturellement les boucles fortes ;
- les modeles de convertisseurs sont souvent statiques ;
- les profils de vitesse sont macroscopiques ;
- les coefficients empiriques doivent encore etre mieux justifies ;
- le mode forward est une extension possible mais moins consolidee ;
- les stockages actifs necessitent une strategie ou un solveur supplementaire.

Ces limites ne sont pas des erreurs de conception. Elles correspondent a un choix
d'incrementalite : produire d'abord un outil clair, fonctionnel et documentable,
puis ajouter de la complexite uniquement la ou elle apporte de la valeur.

## Synthese des choix principaux

| Sujet | Choix retenu | Raison |
| --- | --- | --- |
| Structure globale | Modele systemique modulaire | Permet de raffiner progressivement les blocs |
| Configuration | YAML | Scenarios lisibles, reproductibles et versionnables |
| Coeur de calcul | DAG de bus et convertisseurs | Simple, visuel, robuste pour les chaines energetiques sans boucle |
| Sens des flux | Sens physique dans le YAML | Configuration stable quel que soit le mode de calcul |
| Premier mode de calcul | Inverse statique | Adapte aux profils de mission imposes et aux ordres de grandeur |
| Visualisation | Graphe enrichi avec inputs virtuels | Controle du YAML sans perturber le calcul |
| Profils et signaux | Profiles + adapters + inputs | Separation entre donnees, transformations, conventions de signe et connexion au solver |
| Navigation | Croisiere / Course / Etape | Structure proche des horaires CGN et reutilisable |
| Vitesse | Profil MRUA discret | Compromis simple entre horaire, distance et exploitabilite energetique |
| Stockage | Post-traitement puis evolution possible | Evite les boucles dynamiques au depart |
| Optimisation | Module futur en amont du solver | Conserve le coeur actuel et ajoute les setpoints optimises si besoin |

## Conclusion

Le developpement de CGN-model a suivi une demarche progressive. Le projet est
parti d'une ambition de modele systemique inspiree des outils de simulation
physique, puis s'est volontairement recentre sur une architecture Python simple,
lisible et exploitable.

Le choix central est de representer la chaine energetique par un graphe physique
de bus et convertisseurs, configure par YAML, assemble par un objet `Vessel` et
resolu principalement en mode inverse. Cette architecture permet de produire des
resultats utiles tout en restant comprehensible pour un utilisateur technique.

Les choix effectues privilegient donc la tracabilite, la modularite et
l'incrementalite. Les evolutions plus avancees, comme les stockages actifs,
l'optimisation temporelle ou les solveurs dynamiques, restent compatibles avec
l'architecture, mais ne sont pas imposees au coeur actuel du modele.
