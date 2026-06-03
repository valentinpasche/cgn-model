# Lexique des modules, classes et objets CGN-model

## Perimetre

Ce lexique documente les objets principaux du package `cgn_model`, hors modules
d'interface utilisateur :

- inclus : `energy_solver`, `vessel_model`, `navigation` ;
- exclus : `web_mvp`, `web_ui_v2`.

L'objectif est de donner une definition statique des modules/classes et de leur
role dans l'architecture. Ce document ne remplace pas les docstrings : il sert de
vue explicative pour comprendre les objets et leurs responsabilites.

## Notions transversales

### Vessel

Objet metier principal qui represente un bateau configure pour une simulation.
Dans le code, `Vessel` n'est pas seulement une fiche descriptive du bateau : il
sert d'orchestrateur entre le YAML, les profils, les adapters, les inputs, le
solveur DAG et les stockages.

### Profil

Signal temporel brut ou exogene. Un profil peut etre constant, donne sous forme
de serie, lu depuis un fichier CSV, ou construit depuis les horaires de
navigation CGN. Un profil possede un identifiant, une unite et un vecteur de
donnees.

### Signal

Terme general pour une grandeur 1D materialisee sous forme de tableau numpy avec
une unite. Dans `Vessel`, les signaux regroupent les profils bruts et les sorties
d'adapters.

### Adapter

Transformation entre un ou plusieurs signaux d'entree et un signal de sortie.
Exemples : vitesse vers puissance, vitesse vers force, force et vitesse vers
puissance, vitesse vers rendement. Un adapter ne gere pas la convention de signe
du solver ; il produit une grandeur physique.

### Input

Point d'entree du solveur energetique. Un input est connecte a un bus et recoit
un profil signe. Le signe indique si le profil injecte de la puissance dans le
bus ou s'il represente une demande.

### Bus

Noeud de bilan energetique du solveur. Un bus agrege les injections et retraits
de puissance instantanee. Il porte un identifiant, un carrier descriptif
(`Electrical`, `Mechanical`, `Chemical`, etc.) et un bilan `net_w`.

### Converter

Composant qui relie deux bus et convertit une puissance d'un bus amont vers un
bus aval. Le sens `from_bus -> to_bus` correspond au sens physique nominal. Un
convertisseur expose une methode directe `forward` et une methode inverse
`inverse`.

### DAG

Graphe oriente acyclique utilise pour representer la chaine energetique. Les
aretes correspondent aux convertisseurs et les noeuds aux bus. L'absence de
cycle permet de calculer un ordre d'execution deterministe.

### Plan

Liste ordonnee d'aretes du DAG a parcourir pendant la resolution. En mode
`inverse`, le plan remonte la chaine energetique depuis les besoins aval. En
mode `forward`, il suivrait le sens physique du flux, mais ce mode est marque
non verifie dans le code actuel.

### Ledger

Registre interne d'un bus. Il conserve les contributions par input ou par
convertisseur, ce qui permet de retracer comment le bilan du bus a ete construit.

### Storage

Post-traitement associe a un bus pour calculer des energies cumulees, niveaux de
stockage et conversions eventuelles en masse ou volume. Dans l'architecture
actuelle, le stockage est surtout un objet d'analyse apres resolution.

## Package `cgn_model`

### Module `cgn_model.__init__`

Point d'entree du package. Il expose la version du package via `__version__` et
signale que les sous-domaines principaux sont `energy_solver`, `vessel_model` et
`navigation`.

Il expose aussi `Vessel` comme point d'entree metier principal, ce qui permet
l'import suivant :

```python
from cgn_model import Vessel
```

L'import de `Vessel` est charge a la demande, afin de ne pas importer tout le
modele vessel lors d'un simple `import cgn_model`.

### `__version__`

Version du package Python. Elle sert a identifier la version installee ou
utilisee dans un environnement donne.

### API generale recommandee

Pour un usage metier standard, l'API principale est volontairement courte :

```python
from cgn_model import Vessel

vessel = Vessel.from_yaml(yaml_text)
vessel.run()
df = vessel.results_dataframe()
```

Cette sequence couvre la construction du modele, la resolution du solveur et la
production d'un tableau de resultats.

## Package `cgn_model.energy_solver`

Le package `energy_solver` contient le coeur de preparation et d'execution du
solveur energetique base sur un DAG. Il est volontairement generique : il ne
connait pas la navigation ni les details metier du bateau. Il manipule des bus,
des inputs signes, des convertisseurs et des profils en W.

### Module `energy_solver.__init__`

Expose l'API publique du solveur :

- `SolverDAG`
- `prepare_state`
- `run_vector`
- `attach_eta_profile`

### Module `energy_solver.types`

Regroupe les alias de types utilises par le solveur. Ces alias rendent les
signatures plus lisibles et stabilisent le vocabulaire du code.

### `FArray`

Alias pour un tableau numpy de nombres flottants. Il est utilise pour les
profils temporels et les signaux numeriques.

### `Mode`

Alias litteral pour les modes du solveur : `"forward"` ou `"inverse"`. Le mode
`inverse` est le mode exploite dans les exemples et le mode `forward` est present
dans la structure mais non verifie a l'execution.

### `BusId`, `ConvId`, `Edge`, `PlanItem`, `Plan`

Alias de lisibilite :

- `BusId` : identifiant de bus ;
- `ConvId` : identifiant de convertisseur ;
- `Edge` : tuple `(from_bus, to_bus)` ;
- `PlanItem` : couple `(edge, converter_id)` ;
- `Plan` : liste ordonnee de `PlanItem`.

### `Coord`, `Pos`

Types utilises pour les positions de noeuds lors de l'affichage NetworkX du
graphe.

### Module `energy_solver.config`

Schemas Pydantic de la configuration du solveur. Ce module verifie la forme du
YAML cote solver et certaines contraintes croisees.

### `SolverCfg`

Schema de la section `solver`. Il valide le mode de resolution du DAG.

### `BusCfg`

Schema d'un bus declare dans le YAML. Il valide l'identifiant, le carrier et
l'unite. Pour l'instant, l'unite canonique attendue est `W` pour les carriers
connus.

### `InputCfg`

Schema d'un input du solver. Il contient l'identifiant de l'input et le bus cible
sur lequel le profil sera applique.

### `ConverterCfg`

Schema d'un convertisseur. Il contient :

- `id` : identifiant ;
- `from_bus` : bus amont physique ;
- `to_bus` : bus aval physique ;
- `kind` : type de convertisseur ;
- `params` : parametres specifiques au type.

### `Cfg`

Schema global du solveur DAG. Il regroupe `solver`, `buses`, `converters` et
`inputs`. Il effectue les controles croises :

- tous les bus references par les inputs et convertisseurs doivent exister ;
- les IDs de bus, convertisseurs et inputs ne doivent pas etre dupliques.

### Module `energy_solver.converters`

Contient les classes de convertisseurs energetiques et le registre qui relie un
`kind` YAML a une implementation Python.

### `ConverterABC`

Contrat abstrait d'un convertisseur. Toute implementation doit fournir :

- `forward(p_in_w)` : calcule la puissance de sortie a partir d'une puissance
  prelevee sur le bus amont ;
- `inverse(p_out_w)` : calcule la puissance d'entree necessaire pour obtenir une
  puissance cible sur le bus aval.

Ce contrat garantit que le solveur peut manipuler differents convertisseurs sans
connaitre leur logique interne.

### `LoggedConverter`

Mixin dataclass qui ajoute les tableaux de log communs :

- `p_in_w` : puissance retiree du bus amont ;
- `p_out_w` : puissance injectee sur le bus aval.

Ces attributs sont remplis pendant la resolution.

### `ConverterParams`

Base Pydantic pour les parametres de convertisseurs. Elle interdit les champs
inconnus afin de detecter rapidement les fautes de configuration YAML.

### `REGISTRY`

Dictionnaire global qui associe chaque `kind` de convertisseur a un modele de
parametres et a une fonction builder. Il permet d'ajouter des convertisseurs sans
modifier le coeur du solveur.

### `register`

Decorateur utilise pour inscrire un nouveau type de convertisseur dans
`REGISTRY`.

### `build_converter_from_cfg`

Fonction de construction appelee par `SolverDAG`. Elle lit le `kind`, valide les
`params`, puis instancie le convertisseur correspondant.

### `ConstantEtaParams`

Parametres du convertisseur `constant_eta`. Il contient le rendement `eta`, avec
la contrainte `0 < eta <= 1`.

### `ConstantEtaConverter`

Convertisseur a rendement constant. Il applique :

- `forward(p_in_w) = p_in_w * eta` ;
- `inverse(p_out_w) = p_out_w / eta`.

Il sert aux conversions simples comme moteur, groupe electrogene ou autre bloc
dont le rendement peut etre approxime par une valeur fixe.

### `VariableEtaParams`

Parametres du convertisseur `variable_eta`. Il contient :

- `eta_default` : rendement de repli ;
- `eta_source` : identifiant optionnel du signal de rendement a attacher.

### `VariableEtaConverter`

Convertisseur a rendement variable dans le temps. Si un profil `eta_profile` est
attache, les methodes `forward` et `inverse` utilisent ce profil. Sinon, le
convertisseur utilise `eta_default`.

Il est utile lorsque le rendement depend d'un autre signal, par exemple une
vitesse ou une charge.

### Module `energy_solver.solver_dag`

Prepare le solveur DAG mais ne lance pas la simulation. Il parse et valide la
configuration, construit les objets runtime, cree les graphes et genere le plan
d'execution.

### `Bus`

Conteneur runtime d'un bus energetique. Il contient :

- `id` : identifiant ;
- `carrier` : type descriptif d'energie ;
- `unit` : unite de bilan, actuellement `W` ;
- `net_w` : profil net signe du bus ;
- `ledger` : contributions par input ou convertisseur.

### `Input`

Conteneur runtime d'un input exogene connecte a un bus. Son profil est rempli
plus tard par `prepare_state`, apres construction du solveur.

### `Graphs`

Dataclass regroupant les deux graphes NetworkX :

- `exec` : graphe d'execution, limite aux bus et convertisseurs ;
- `view` : graphe de visualisation, enrichi avec les inputs virtuels.

### `SolverDAG`

Objet de preparation du solveur. Il contient :

- le mode de resolution ;
- les bus ;
- les convertisseurs ;
- les inputs ;
- les graphes ;
- le plan d'execution.

Sa methode publique principale est `from_yaml`, qui orchestre :

1. normalisation du YAML ;
2. validation Pydantic ;
3. construction des objets ;
4. construction des graphes ;
5. creation du plan.

### `SolverDAG.from_yaml`

Construit un `SolverDAG` depuis une chaine YAML ou un dictionnaire. Cette methode
prepare la structure, mais n'applique pas encore les profils et ne lance pas
`run_vector`.

### `SolverDAG.draw_dag`

Affiche le graphe `exec` ou `view` avec NetworkX/Matplotlib. Le graphe `view`
permet notamment de voir les inputs connectes aux bus.

### Fonctions internes de `SolverDAG`

- `_parse_cfg` : isole et normalise les sections utiles au solveur ;
- `_validate_cfg` : valide ces sections avec Pydantic ;
- `_build_objects` : instancie bus, convertisseurs et inputs ;
- `_build_graphs` : construit les graphes d'execution et de visualisation ;
- `_build_plan` : calcule l'ordre des convertisseurs selon le mode.

Ces fonctions sont internes mais importantes pour comprendre la separation des
responsabilites.

### Module `energy_solver.run_dag`

Contient l'execution vectorielle du solveur. Contrairement a `solver_dag.py`, ce
module modifie les etats numeriques des bus et des convertisseurs.

### `_pos`

Fonction utilitaire interne qui retourne la partie positive d'un tableau.

### `_neg_mag`

Fonction utilitaire interne qui retourne la magnitude de la partie negative d'un
tableau. Elle sert a identifier les deficits de puissance a couvrir.

### `prepare_state`

Prepare les etats numeriques du solveur avant resolution :

- valide les profils fournis ;
- verifie les longueurs ;
- initialise les `net_w` des bus ;
- reinitialise les logs des convertisseurs ;
- attache les profils aux inputs ;
- ajoute les contributions d'inputs aux bus.

Cette fonction est appelee par le `Vessel` lors de la preparation du solver.

### `run_vector`

Execute la propagation vectorielle des puissances sur le DAG. En mode `inverse`,
elle parcourt le plan, identifie les deficits aval et remonte les besoins vers
les bus amont via `conv.inverse`.

Elle met a jour :

- `bus.net_w` ;
- `conv.p_in_w` ;
- `conv.p_out_w` ;
- `bus.ledger`.

Le mode `forward` est present dans le code mais leve actuellement une erreur car
il n'est pas encore valide sur un cas physique de reference.

Dans l'usage metier courant, `run_vector` est appele indirectement par
`Vessel.run()`. L'appel direct reste utile pour un usage avance du solveur, par
exemple pour inspecter ou modifier l'etat du `SolverDAG` avant ou apres
resolution.

### `attach_eta_profile`

Fonction utilitaire qui attache un profil de rendement `eta(t)` a un
convertisseur `variable_eta`. Elle verifie l'existence du convertisseur, la
dimension 1D du profil et borne les valeurs dans `[0, 1]`.

## Package `cgn_model.vessel_model`

Le package `vessel_model` relie la configuration metier et le solveur. Il gere
les profils, les adapters, les bindings d'inputs, les stockages et
l'orchestration globale.

### Module `vessel_model.__init__`

Expose l'API publique du package vessel : `Vessel`.

### Module `vessel_model.profiles`

Contient les objets et fonctions de preparation des profils d'entree du
`Vessel`.

Ce module regroupe les traitements qui transforment une declaration de profil en
donnees numeriques utilisables par le modele : valeurs constantes, series,
colonnes CSV et profils de vitesse issus de la navigation.

L'interet de ce module est de separer la preparation des profils de
l'orchestration generale effectuee dans `vessel.py`.

### `Profile`

Dataclass runtime d'un profil brut. Elle contient :

- `id` : identifiant du profil ;
- `unit` : unite associee ;
- `data` : tableau numpy contenant les valeurs du profil.

Un `Profile` represente donc une grandeur exogene deja materialisee, mais pas
encore forcement connectee au solveur.

### `_load_csv_column`

Fonction interne qui charge une colonne numerique depuis un fichier CSV.

Elle est utilisee par les profils de type `file`. Elle centralise la lecture du
fichier, le choix de la colonne, le separateur, l'encodage et la conversion vers
un tableau numerique.

### `_build_nav_speed`

Fonction interne qui construit un profil de vitesse depuis le module
`navigation`.

Elle traduit une configuration `nav_speed` en profil discret de vitesse, en
selectionnant la croisiere, la course ou l'etape demandee, puis en appelant les
objets de navigation appropries.

### `_pick_master_id`

Fonction interne qui choisit le profil maitre utilise pour fixer la longueur
temporelle du scenario.

Elle permet de savoir quel profil sert de reference lorsque certaines donnees
constantes doivent etre etendues ou lorsque plusieurs series doivent etre
comparees en longueur.

### Module `vessel_model.signals`

Contient les objets de liaison entre profils/adapters et inputs du solveur, ainsi
que les fonctions liees aux conventions de signe.

Ce module isole une partie sensible du modele : la distinction entre une
grandeur physique produite par un profil ou un adapter, et le signal signe qui
est effectivement injecte dans un bus du solveur.

### `InputBind`

Dataclass runtime d'une liaison entre un input solver et une source de signal.

Elle indique :

- l'identifiant de l'input solver ;
- le bus cible ;
- la source utilisee ;
- la convention de signe ;
- le facteur d'echelle eventuel.

Le `sign` et le `scale` sont appliques lors de la preparation des profils du
solveur.

### `Signals`

Alias pour le dictionnaire des signaux materialises :
`id -> (array, unit)`.

Il regroupe les profils bruts et les sorties d'adapters sous une forme commune,
afin que les inputs puissent ensuite pointer vers n'importe quelle source
declaree.

### `_apply_sign_policy`

Fonction interne qui applique la convention de signe d'un input.

Elle gere les politiques `consume`, `inject` et `as_is`. Elle transforme donc une
grandeur physique en signal signe compatible avec la convention du solveur :
positif pour une injection, negatif pour une consommation.

### `_warn_inconsistent_sign`

Fonction interne qui emet un avertissement lorsqu'un profil semble incoherent
avec la convention de signe declaree.

Elle ne bloque pas l'execution, mais aide a detecter les configurations
ambiguës, par exemple un profil majoritairement negatif declare comme injection.

### Module `vessel_model.config`

Schemas Pydantic des sections metier du YAML : `vessel`, `simulation`,
`profiles`, `adapters`, `inputs` et `storages`.

### `VesselType`

Type litteral des familles de propulsion reconnues : `"DE"`, `"steam"` ou
`"undefined"`.

### `MULTISOURCE_KINDS`

Dictionnaire qui declare les adapters multi-entrees et les cles de `params`
contenant leurs sources. Il permet a la validation YAML de connaitre les
dependances reelles d'un adapter multi-source.

### `VesselCfg`

Schema des metadonnees du bateau : nom et type de vessel.

### `SimulationCfg`

Schema des parametres globaux de simulation. Il contient actuellement le pas de
temps `dt`, strictement positif et exprime en secondes.

### `ProfileCfgBase`

Base commune des profils. Elle porte l'identifiant, l'unite, d'eventuelles
donnees et le flag `master`.

### `ConstantProfileCfg`

Schema d'un profil constant. Il contient une valeur scalaire ou une liste. Les
profils constants peuvent etre ajustes a la longueur du profil maitre.

### `SeriesProfileCfg`

Schema d'un profil explicite sous forme de liste de valeurs.

### `FileProfileCfg`

Schema d'un profil charge depuis un fichier CSV. Il gere le fichier, la colonne,
le separateur, le separateur decimal et l'encodage.

### `NavParams`

Parametres optionnels pour generer un profil de vitesse depuis la navigation :
acceleration, deceleration, vitesse de croisiere et autorisation de retard.

### `NavSelectCruise`

Schema de selection d'une croisiere par nom.

### `NavSelectCourse`

Schema de selection d'une course par numero.

### `NavSelectLeg`

Schema de selection d'une etape par couple `from_port` / `to_port`.

### `NavSelect`

Union discriminee des trois schemas de selection navigation. Le champ `by`
determine le type de selection.

### `NavSpeedProfileCfg`

Schema d'un profil `nav_speed`. Il permet de construire un profil de vitesse
depuis les horaires CGN embarques, avec selection par croisiere, course ou
etape.

### `ProfileCfg`

Union discriminee des types de profils disponibles : `constant`, `series`,
`file`, `nav_speed`.

### `AdapterCfg`

Schema generique d'un adapter YAML. Il contient `id`, `kind`, `source`,
`unit_in`, `unit_out` et `params`.

### `InputBindCfg`

Schema d'une liaison entre un input du solver et une source de signal. Il
contient :

- `id` : identifiant de l'input solver ;
- `bus` : bus cible ;
- `source` : profil ou adapter ;
- `sign` : `consume`, `inject` ou `as_is` ;
- `scale` : facteur optionnel.

Il normalise certains synonymes de signe comme `load`, `sink`, `source`,
`supply`.

### `EnergyVectorParams`

Schema des parametres physiques d'un vecteur energetique stocke. Il decrit le
PCI massique ou volumique et la densite eventuelle. Il verifie que les champs
PCI sont coherents avec la base choisie.

### `InitialStorageLevel`

Schema d'un niveau initial de stockage. Le niveau peut etre donne en energie,
masse ou volume.

### `StorageCfg`

Schema d'un stockage rattache a un bus. Il contient l'identifiant du stockage,
le bus cible, le nom du vecteur energetique, les parametres physiques et le
niveau initial optionnel. Il accepte aussi des alias historiques comme
`vecteur`, `vector` ou `vector_name`.

### `VesselSectionsCfg`

Schema global des sections metier du YAML. Il verifie :

- unicite des IDs ;
- absence de collision entre profiles, adapters et storages ;
- existence des sources d'adapters ;
- absence de cycle dans le graphe profiles/adapters ;
- existence des sources referencees par les inputs.

### Module `vessel_model.adapters`

Contient les adapters runtime et le registre qui associe les `kind` YAML aux
implementations Python.

### `convert_unit`

Fonction de conversion d'unites stricte. Elle gere actuellement trois grandeurs :

- puissance ;
- vitesse ;
- force.

Elle refuse les ecritures SI ambigues afin d'eviter des erreurs de facteur.

### Fonctions internes `_canon_*` et `_parse_unit`

Fonctions de normalisation et de validation des unites. Elles sont internes au
module et servent a `convert_unit`.

### `AdapterABC`

Contrat abstrait d'un adapter runtime. Il definit :

- `required_sources` : liste des sources necessaires ;
- `apply` : transformation mono-entree ;
- `apply_multi` : transformation multi-entrees.

Un adapter mono-source surcharge `apply`. Un adapter multi-source surcharge
`required_sources` et `apply_multi`.

### `AdapterParams`

Base Pydantic pour les parametres d'adapters. Elle interdit les champs inconnus.

### `REGISTRY`

Registre des adapters disponibles. Il mappe `kind -> (ParamsModel, builder)`.

### `register`

Decorateur d'enregistrement d'un adapter.

### `build_adapter_from_cfg`

Construit un adapter runtime depuis une configuration `AdapterCfg`. Il valide les
parametres et instancie l'implementation correspondant au `kind`.

### `SpeedToPowerPolyParams`

Parametres de l'adapter `speed_to_power_poly` : coefficients polynomiaux et
valeur minimale optionnelle.

### `SpeedToPowerPolyAdapter`

Adapter vitesse vers puissance. Il convertit la vitesse vers `unit_in`, applique
un polynome `P(v)`, clippe eventuellement la sortie, puis convertit vers
`unit_out`.

### `ForceAndSpeedToPowerParams`

Parametres de l'adapter multi-entrees `force_and_speed_to_power`. Il declare les
sources force et vitesse, leurs unites attendues et le clip optionnel.

### `ForceAndSpeedToPowerAdapter`

Adapter qui calcule une puissance par `P = F * v`. Il lit deux sources, force et
vitesse, les convertit en unites attendues, puis produit une puissance.

### `SpeedToForcePolyParams`

Parametres de l'adapter `speed_to_force_poly` : coefficients polynomiaux et clip
optionnel.

### `SpeedToForcePoly`

Adapter vitesse vers force. Il applique un polynome `F(v)` apres conversion de
la vitesse.

### `SpeedToEtaPolyParams`

Parametres de l'adapter `speed_to_eta_poly`. Il contient les coefficients du
polynome de rendement.

### `SpeedToEtaPoly`

Adapter vitesse vers rendement. Il produit un profil adimensionnel `eta(v)` qui
peut ensuite etre attache a un convertisseur `variable_eta`.

### `PowerToPowerPolyParams`

Parametres de l'adapter `power_to_power_poly` : coefficients polynomiaux et clip
optionnel.

### `PowerToPowerPolyAdapter`

Adapter puissance vers puissance. Il applique un polynome sur une puissance
d'entree, utile pour representer une relation empirique entre deux niveaux de
puissance.

### Module `vessel_model.energy_units`

Utilitaires de conversion d’unités énergétiques, principalement utilisés pour
les niveaux et vecteurs de stockage.

### `PCI_Massic_Unit`

Type litteral des unites de PCI massique acceptees : `kWh/kg`, `MJ/kg`,
`kJ/kg`, `J/kg`.

### `PCI_Volumic_Unit`

Type litteral des unites de PCI volumique acceptees : `kWh/l`, `kWh/m3`,
`MJ/m3`, `kJ/m3`, `J/m3`.

### `StorageLevelUnit`

Type litteral des unites possibles pour un niveau initial : energie, masse ou
volume.

### `pci_to_j_per_kg`

Convertit un PCI massique vers `J/kg`.

### `pci_to_j_per_m3`

Convertit un PCI volumique vers `J/m3`.

### `energy_to_j`

Convertit une energie donnee en `J`, `kJ`, `MJ`, `Wh`, `kWh` ou `MWh` vers des
Joules.

### `level_to_j`

Convertit un niveau initial de stockage vers des Joules. Le niveau peut etre
donne en energie, masse ou volume. Les conversions masse/volume exigent un PCI
et parfois une densite.

### Module `vessel_model.results_utils`

Contient les utilitaires de nommage des colonnes de resultats et de gestion des
unites dans les exports tabulaires.

Ce module est utilise notamment par `Vessel.results_dataframe()`. Il permet de
centraliser les conventions d'affichage des colonnes, au lieu de les laisser
dans la methode principale d'export.

### `clean_unit_syntax`

Normalise l'ecriture d'une unite pour l'affichage.

Cette fonction nettoie les details de syntaxe issus du stockage interne afin de
produire des libelles plus lisibles dans les noms de colonnes.

### `results_col_name`

Construit un nom de colonne de resultats a partir d'un nom logique et d'une
unite.

La convention obtenue est du type `nom [unite]` lorsque l'unite est disponible.

### `unit_from_storage_col`

Extrait l'unite contenue dans un nom de colonne issu d'un `StorageResult`.

Elle sert a recuperer l'information d'unite avant de reconstruire un nom de
colonne final dans le DataFrame global.

### `strip_storage_unit_suffix`

Retire le suffixe d'unite d'un nom de colonne de stockage.

Cette fonction permet de retrouver le nom logique de la grandeur, independamment
de l'unite ajoutee lors du post-traitement.

### Module `vessel_model.storage`

Contient le post-traitement des bus de stockage.

### `StorageResult`

Resultat de stockage associe a un bus. Il calcule :

- puissance signee ;
- parties positive et negative ;
- energie cumulee ;
- niveau de stockage avec niveau initial ;
- conversions optionnelles en masse et volume ;
- resume textuel et export DataFrame.

Il est construit via `StorageResult.from_bus`, puis peut etre exporte avec
`to_dataframe` ou resume avec `summary_dict`.

### `StorageResult.from_bus`

Construit un `StorageResult` a partir du `net_w` d'un bus, du pas de temps, des
parametres de vecteur energetique et du niveau initial.

### `StorageResult.to_dataframe`

Retourne un DataFrame contenant les colonnes de stockage standardisees.

### `StorageResult.summary_dict`

Retourne les indicateurs principaux sous forme de dictionnaire : energies
totales, pics de puissance, niveau initial et final, masse ou volume net si
disponible.

### `StorageResult.summary`

Propriete d'affichage qui imprime un resume lisible en console.

### Module `vessel_model.vessel`

Orchestrateur metier du modele. Il relie YAML, profils, adapters, inputs,
solveur et stockages.

Depuis le refactor, `vessel.py` conserve le role de coordination principale,
tandis que plusieurs traitements auxiliaires sont deplaces dans des modules
dedies :

- `profiles.py` pour la preparation des profils ;
- `signals.py` pour les bindings d'inputs et les conventions de signe ;
- `results_utils.py` pour le nommage des resultats et les unites.

### `Vessel`

Classe principale du package vessel. Elle contient :

- les metadonnees du bateau ;
- le solveur DAG ;
- le pas de temps ;
- les profils ;
- les adapters ;
- les bindings d'inputs ;
- les signaux materialises ;
- les configurations et resultats de stockage.

### `Vessel.t`

Propriete qui retourne le vecteur temps en secondes si les profils du solver
sont initialises.

### `Vessel.from_yaml`

Construit un `Vessel` complet depuis un YAML texte ou un dictionnaire. La methode
valide les metadonnees, construit le `SolverDAG`, valide les sections metier,
instancie les profils/adapters/bindings et materialise les signaux.

### `Vessel.run`

Execute le workflow metier principal du vessel.

Cette methode prepare le solver interne, lance la resolution vectorielle avec
`run_vector`, puis calcule les stockages configures. Elle permet de masquer les
details du `SolverDAG` pour l'utilisateur courant.

Usage recommande :

```python
vessel = Vessel.from_yaml(yaml_text)
vessel.run()
df = vessel.results_dataframe()
```

### `Vessel.build_solver_inputs`

Construit le mapping des profils signes destines aux inputs du solver. Cette
methode applique les conventions de signe et les facteurs d'echelle. Elle peut
retourner soit un mapping complet avec les bus, soit uniquement les profils.

### `Vessel.apply_inputs_to_solver`

Applique les inputs au `SolverDAG` via `prepare_state`. Elle peut aussi attacher
automatiquement les profils de rendement aux convertisseurs `variable_eta`.

### `Vessel.attach_converter_eta_profiles`

Attache les profils `eta(t)` aux convertisseurs qui declarent une `eta_source`.
C'est le lien entre les adapters de rendement et les convertisseurs a rendement
variable.

### `Vessel.build_solver`

Orchestrateur court qui prepare le solver interne. Il applique les inputs et
attache les rendements variables, mais ne lance pas `run_vector`.

Cette methode est surtout utile pour un usage avance, lorsque l'utilisateur veut
inspecter ou modifier le solver avant la resolution.

### `Vessel.tally_storages`

Construit les `StorageResult` a partir des bus references dans `storages_cfg`.
Cette methode est a appeler apres preparation du solver, et selon le cas apres
`run_vector`, pour obtenir les resultats de stockage.

Dans l'usage courant, cette methode est appelee automatiquement par
`Vessel.run()`.

### `Vessel.results_dataframe`

Compile les resultats principaux dans un DataFrame plat :

- temps ;
- profils ;
- adapters ;
- inputs solver ;
- convertisseurs ;
- stockages.

Les unites sont conservees dans `df.attrs["units"]`.

### Fonctions internes de `vessel.py`

- `_parse_cfg` / `_validate_cfg` : traitent les metadonnees du vessel ;
- `_extract_sections` : isole les sections metier du YAML ;
- `_check_id_collisions` : detecte les collisions d'IDs entre sections ;
- `_build_profiles` : construit les profils runtime ;
- `_build_adapters` : construit les adapters runtime ;
- `_build_input_binds` : construit les liaisons input/source ;
- `_materialize_signals` : calcule les profils bruts et sorties d'adapters.

Ces fonctions sont internes mais structurantes pour comprendre le pipeline
`YAML -> Vessel -> SolverDAG`.

Les helpers de profils, de signes et de resultats sont documentes dans les
sections `vessel_model.profiles`, `vessel_model.signals` et
`vessel_model.results_utils`.

## Package `cgn_model.navigation`

Le package `navigation` transforme des horaires CGN en objets de navigation et
en profils de vitesse.

### Module `navigation.__init__`

Expose l'API publique :

- `Etape`
- `Course`
- `Croisiere`
- `SpeedProfileParams`

### Module `navigation.cruise_model`

Contient les objets de navigation et la logique de generation de profils de
vitesse.

### `format_profile_summary`

Fonction utilitaire qui resume un profil numpy 1D sous forme courte. Elle sert
aux representations `repr` des objets navigation.

### `_cgn_croisiere_csv_path`

Fonction interne qui retourne le chemin d'un fichier CSV embarque dans le
package.

### `SpeedProfileParams`

Parametres de generation d'un profil de vitesse MRUA :

- `dt` : pas de temps ;
- `acc` : acceleration ;
- `dec` : deceleration ;
- `v_croisiere` : vitesse maximale visee ;
- `v_moyenne_horaire` : vitesse moyenne de reference optionnelle ;
- `allow_delay` : autorisation de retard.

### `Etape`

Segment elementaire de navigation entre deux ports, ou pause si `km == 0`.
L'objet porte :

- port de depart ;
- port d'arrivee ;
- heure de depart ;
- distance ;
- duree ;
- profil de vitesse eventuel ;
- retard eventuel.

La methode `speed_profile` genere un profil de vitesse pour cette etape. Pour une
pause, le profil est nul. Pour une navigation, le profil est base sur une
hypothese MRUA avec acceleration, plateau eventuel et deceleration.

### `Course`

Sequence d'etapes correspondant a un numero de course. Elle fournit des
proprietes derivees : ports de depart/arrivee, duree, distance totale, temps de
navigation, temps de pause et vitesse moyenne.

Sa methode `speed_profile` concatene les profils des etapes.

### `Croisiere`

Ensemble de courses et de pauses inter-courses. Elle reconstruit un `trajet`
chronologique mixte contenant des `Course` et des `Etape` de pause, sans
dupliquer les objets.

Elle fournit :

- `from_port`, `to_port` ;
- `trajet` ;
- `all_etapes` ;
- totaux de distance et de temps ;
- vitesse moyenne ;
- affichage lisible ;
- construction depuis DataFrame ou CSV ;
- generation du profil de vitesse complet.

### `Croisiere.from_df`

Construit des croisieres depuis un DataFrame contenant les colonnes horaires
CGN. Le modele interprete les lignes comme des transitions de la ligne `i` vers
la ligne `i+1`.

### `Croisiere.from_csv`

Charge un CSV local puis appelle `from_df`. La colonne `horaire` est parse au
format `HHhMM` comme heure locale naive.

### `Croisiere.from_cgn_croisiere_csv`

Charge un CSV embarque dans le package, par exemple `all.csv`, puis construit les
objets de navigation.

### `Croisiere.check_continuite`

Verifie que les ports s'enchainent correctement dans le trajet.

### `Croisiere.speed_profile`

Concatene les profils de toutes les courses et pauses pour obtenir le profil de
vitesse complet d'une croisiere.
