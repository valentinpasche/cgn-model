# Exemple SolverDAG autonome

Cet exemple utilise directement le solveur énergétique, sans construire de
`Vessel`.

Il illustre l'API publique minimale :

```python
solver = SolverDAG.from_yaml(yaml_text)
prepare_state(solver, input_profiles)
run_vector(solver)
```

Le YAML décrit uniquement la topologie énergétique :

```text
fuel -> genset -> elec_power -> motor -> shaft
```

Les profils sont créés directement dans le script. Ils respectent la convention
du solveur :

- valeur négative : demande sur un bus ;
- valeur positive : injection sur un bus.

Le script :

- construit le DAG et son plan d'exécution ;
- applique une demande mécanique et une charge électrique ;
- résout les besoins amont en mode `inverse` ;
- rassemble quelques résultats dans un DataFrame ;
- vérifie les rendements et bilans avec des assertions NumPy.

Exécution depuis la racine du dépôt :

```text
python examples/solver_dag_mode_260605/run.py
```

L'affichage graphique du DAG et l'export CSV sont disponibles sous forme de
lignes commentées dans le script.
