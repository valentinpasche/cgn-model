# Documentation CGN-model

Cette page sert de point d'entree pour la documentation statique du modele CGN.
Le README du depot reste la reference pour l'installation rapide et les commandes
de lancement. Cette page oriente plutot vers les guides de configuration,
d'utilisation et de comprehension du modele.

## Vue d'ensemble

CGN-model est un package Python de simulation de chaine energetique pour bateau.
Le modele s'articule autour de trois blocs :

- `vessel_model` charge une configuration YAML et assemble les profils, adapters,
  inputs, buses, convertisseurs et stockages.
- `energy_solver` resout les flux d'energie sur un DAG de bus et convertisseurs.
- `navigation` construit des profils de vitesse a partir d'horaires CGN embarques.

API utilisateur principale :

```python
from cgn_model import Vessel

vessel = Vessel.from_yaml(yaml_text)
vessel.run()
df = vessel.results_dataframe()
```

Les appels plus detailles comme `build_solver()`, `run_vector()` ou
`tally_storages()` restent disponibles pour l'inspection et les usages avances,
mais ne sont pas necessaires pour l'utilisation courante.

## Guides disponibles

- [Guide YAML](yaml_guide.md) : structure complete d'un fichier de configuration.
- [Guide navigation](navigation_guide.md) : donnees CGN, selection de croisiere,
  course ou etape, et generation de profils `nav_speed`.
- [Exemple V1](example_v1.md) : exemple complet depuis un YAML jusqu'au CSV de
  resultats.
- [Forward vs inverse](forward_vs_inverse.md) : explication des modes de
  resolution avec exemples numeriques.

## Parcours conseille

Pour une premiere prise en main :

1. Lire le [Guide YAML](yaml_guide.md) pour comprendre la structure d'un
   scenario.
2. Parcourir l'[Exemple V1](example_v1.md) pour voir un cas complet.
3. Lire le [Guide navigation](navigation_guide.md) si le scenario utilise un
   profil `nav_speed`.
4. Consulter la note [forward vs inverse](forward_vs_inverse.md) si
   le fonctionnement du solveur DAG doit etre explique plus en detail.

## Exemples de reference

- `examples/cgn_model_v1_251222/` : exemple V1 documente.
- `examples/configurations_type_260106/` : configurations types.
- `examples/demo_solver_dag_251128/` : exemple centre sur le solveur DAG.
- `examples/cgn_copil_251212/` : exemple de configuration et resultats COPIL.

## Conventions importantes

- Les configurations sont decrites en YAML.
- Le pas de temps `simulation.dt` est exprime en secondes.
- Les profils `nav_speed` utilisent les unites SI : vitesse en `m/s`,
  acceleration et deceleration en `m/s^2`.
- Le mode solver recommande dans les YAML documentes est `inverse`.
- Les bus et convertisseurs du DAG doivent suivre le sens physique du flux
  d'energie avec `from_bus -> to_bus`.
- Les inputs utilisent une convention de signe : `consume`, `inject` ou `as_is`.
