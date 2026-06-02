# Points d'amélioration pour la lisibilité du code

## Objectif

Ce document liste les points qui peuvent rendre le code CGN-model difficile à
comprendre pour un lecteur externe, ainsi que les ajustements possibles pour
améliorer sa lisibilité et son appropriation.

## 1. Clarifier le vocabulaire

Le code utilise plusieurs notions qui sont cohérentes dans l'architecture, mais
qui demandent une définition explicite :

- `profile`
- `signal`
- `adapter`
- `input`
- `binding`
- `bus`
- `converter`
- `storage`
- `ledger`
- `DAG`
- `Vessel`

Ces termes devraient être systématiquement définis dans la documentation. Le
lexique ajouté dans `lexique_modules_classes.md` répond déjà en partie à ce
besoin.

## 2. Expliquer le pipeline global

Le pipeline général est clair une fois connu, mais il n'est pas évident au
premier contact :

```text
YAML -> Vessel.from_yaml() -> Vessel.run() -> Vessel.results_dataframe()
```

Ce flux est maintenant plus simple du point de vue utilisateur. Le pipeline
interne reste plus détaillé :

```text
YAML -> profiles/adapters/signals -> SolverDAG -> run_vector -> storages -> results_dataframe
```

Un schéma ou une courte page dédiée à ce flux aiderait fortement un utilisateur à
comprendre où se situe chaque objet et à distinguer l'API principale de la
mécanique interne.

## 3. Rendre explicite la séparation `Vessel` / `SolverDAG`

Le `Vessel` fait le lien entre le métier et le calcul. Le `SolverDAG`, lui, ne
traite que des bus, convertisseurs et profils signés.

Cette séparation est importante, mais peut être confuse car les deux objets sont
construits depuis le même YAML. Il faut donc bien expliquer que :

- certaines sections YAML sont utilisées par `Vessel` ;
- certaines sections YAML sont utilisées par `SolverDAG` ;
- `Vessel` prépare les signaux avant de les transmettre au solver.

## 4. Documenter le mode inverse avec un exemple simple

Le mode inverse est probablement l'un des points les moins intuitifs.

Le YAML décrit les flux dans le sens physique, par exemple :

```text
Chemical:fuel -> Electrical:main -> Mechanical:shaft
```

Mais en mode inverse, le solveur part d'une demande aval et remonte vers l'amont.
Ce choix est pertinent, mais il doit être expliqué avec un cas minimal chiffré :

- demande mécanique ;
- rendement moteur ;
- demande électrique correspondante ;
- rendement groupe ;
- besoin chimique correspondant.

Il faut aussi rappeler explicitement que le mode `forward` existe dans la
structure du solveur, mais qu'il n'est pas encore validé comme mode de référence
dans l'état actuel du code. Cela évite qu'un lecteur interprète sa présence dans
la configuration comme une fonctionnalité équivalente au mode `inverse`.

## 5. Clarifier les conventions de signe

Les conventions de signe sont un point sensible :

- puissance positive = injection sur un bus ;
- puissance négative = demande ou retrait ;
- `consume` force un profil en négatif ;
- `inject` force un profil en positif ;
- `as_is` conserve le signe fourni.

Les stockages ajoutent une difficulté supplémentaire, car le sens physique
"stockage qui se remplit" ou "stockage qui se vide" doit être relié au signe du
bus. Cette convention devrait être documentée avec un tableau et un exemple.

Pour les stockages, il faudrait notamment préciser :

- le signe associé à un stockage qui se charge ;
- le signe associé à un stockage qui se décharge ;
- le lien entre ce signe et la convention générale des bus ;
- les conventions de PCI massique/volumique utilisées pour chaque vecteur
  énergétique nommé (`diesel`, `H2`, batterie, etc.) ;
- le rôle éventuel des densités dans les conversions masse/volume.

## 6. Garder `Vessel` comme orchestrateur

Le `Vessel` est cohérent comme orchestrateur, mais il concentre beaucoup de
responsabilités :

- parsing partiel du YAML ;
- validation ;
- construction des profils ;
- construction des adapters ;
- matérialisation des signaux ;
- application des inputs ;
- attachement des rendements variables ;
- gestion des stockages ;
- export DataFrame.

Ce n'est pas forcément un problème, mais pour un lecteur externe il faut le
documenter comme tel et éviter que de nouvelles règles transversales soient
ajoutées directement dans cette classe.

Une première extraction a déjà été faite :

- `profiles.py` porte les helpers de profils ;
- `signals.py` porte les bindings d'inputs et les conventions de signe ;
- `results_utils.py` porte les conventions de nommage des résultats et des
  unités.

Le point de vigilance restant est de conserver cette direction : `Vessel` doit
rester le point d'entrée qui orchestre, tandis que les règles techniques
réutilisables doivent rester dans des modules dédiés.

## 7. Harmoniser le vocabulaire anglais/français

Le code mélange volontairement ou historiquement des termes anglais et français :

- `Vessel`, `Profile`, `InputBind`, `StorageResult` ;
- `Croisiere`, `Course`, `Etape` ;
- `vecteur`, `vector_energy`, `vessel_type`, `adapter`.

Ce mélange n'est pas bloquant techniquement, mais il peut donner une impression
moins homogène. Une amélioration possible est de fixer une règle :

- objets Python plutôt en anglais ;
- notions métier CGN/navigation en français ;
- documentation en français avec rappel des noms Python.

## 8. Distinguer les objets publics et internes

Certains objets sont destinés à être utilisés directement par l'utilisateur,
d'autres sont des détails d'implémentation.

Une première clarification a été faite avec l'API principale :

```python
from cgn_model import Vessel

vessel = Vessel.from_yaml(yaml_text)
vessel.run()
df = vessel.results_dataframe()
```

Il reste utile d'indiquer dans la documentation :

- API métier principale : `Vessel.from_yaml`, `Vessel.run`,
  `Vessel.results_dataframe` ;
- API avancée : `SolverDAG`, `run_vector`, `build_solver`,
  `tally_storages`, `Croisiere`, etc. ;
- objets de configuration : classes Pydantic ;
- helpers internes : fonctions préfixées par `_`.

Cela permet au lecteur de savoir ce qu'il peut utiliser directement et ce qui
sert seulement à comprendre le fonctionnement interne.

## 9. Documenter les limites connues

Plusieurs limites sont connues et assumées :

- mode `forward` non validé ;
- coefficients polynomiaux à justifier ;
- profils de vitesse macroscopiques ;
- gestion du retard à clarifier métier ;
- conventions de stockage à confirmer ;
- absence de solveur pour boucles fortes.

Les documenter explicitement est préférable à les laisser implicites. Cela montre
que ces points sont identifiés et qu'ils relèvent de choix ou d'évolutions
futures.

## 10. Documenter les coefficients et domaines de validité

Les adapters empiriques utilisent des coefficients polynomiaux. Pour qu'un
lecteur puisse juger les résultats, il faudrait documenter pour chaque jeu de
coefficients :

- l'origine des coefficients ;
- l'unité d'entrée attendue ;
- l'unité de sortie produite ;
- la plage de validité ;
- les hypothèses d'essai ou de calibration ;
- le sens physique d'un éventuel clip à 0.

Le dernier point est important : un clip peut représenter une hypothèse physique,
un garde-fou numérique ou une convention de post-traitement. Ces trois cas n'ont
pas la même signification pour l'utilisateur.

## 11. Préciser les hypothèses de navigation

Les profils de vitesse issus de la navigation reposent sur une approximation
MRUA. La documentation devrait confirmer explicitement :

- accélération et décélération constantes ;
- repère longitudinal simplifié ;
- absence de courant ;
- absence de correction fine des manœuvres ;
- interprétation des horaires comme heures locales naïves, sans date civile, si
  c'est bien la convention retenue.

La politique de retard devrait aussi être décrite plus précisément :

- quand un retard est reporté ;
- quand il peut être rattrapé sur les pauses ;
- quelle interprétation opérationnelle donner aux secondes supprimées ou
  compensées.

## 12. Consolider la vérification

Les fichiers sous `tests/` semblent en partie jouer le rôle de scripts de
validation manuelle. Avant de poursuivre des refactors importants ou de figer la
documentation finale, il serait utile d'ajouter quelques assertions `pytest` sur
des sorties numériques de référence.

Ces tests devraient couvrir au minimum :

- un cas simple de mode inverse ;
- les conventions de signe `consume`, `inject`, `as_is` ;
- un adapter polynomial représentatif ;
- un stockage avec conversion d'énergie ;
- l'export `results_dataframe()`.

La vérification automatique complète doit être relancée dans l'environnement
Conda du projet. L'environnement shell utilisé pour cette passe documentaire ne
fournissait pas `python` ni `git`, ce qui limite les contrôles exécutables depuis
ce contexte.

## Synthèse

Le code repose sur une architecture cohérente, mais il n'est pas immédiatement
autoportant pour un lecteur externe. La documentation doit donc rendre explicite
le modèle mental suivant :

- le YAML décrit le système et le scénario ;
- le `Vessel` orchestre la traduction de ce scénario en signaux et expose
  `run()` comme workflow principal ;
- le `SolverDAG` résout les bilans de puissance ;
- les stockages et exports transforment les résultats en indicateurs.

Les priorités documentaires les plus utiles sont donc :

1. schéma du pipeline global ;
2. exemple minimal du mode inverse ;
3. tableau des conventions de signe ;
4. distinction entre `Vessel` et `SolverDAG` ;
5. lexique des objets et modules ;
6. fiche des coefficients et domaines de validité ;
7. hypothèses de navigation et politique de retard ;
8. tests numériques de référence.
