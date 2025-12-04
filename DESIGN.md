# DESIGN — cgn_model

Ce fichier documente l’architecture du projet, dossiers et fichiers

---

## 📁 Organisation du projet

```text
cgn-model/
├── .gitattributes
├── .gitignore
├── DESIGN.md
├── README.md
├── dev/
│   ├── data/
│   │   ├── length_TLM_OSM.csv
│   │   └── ...
│   ├── cgn_courses_croisieres.py
│   └── extract_route_cgn_tlm_osm.py
├── docs/
│   └── forward_vs_inverse.md
├── environment.yml
├── examples/
│   ├── config_demo_solver_dag.yaml
│   └── demo_solver_dag.py
├── pyproject.toml
├── src/
│   └── cgn_model/
│       ├── __init__.py
│       ├── energy_solver/
│       │   ├── __init__.py
│       │   ├── components/
│       │   │   ├── __init__.py
│       │   │   └── converters.py
│       │   ├── config.py
│       │   ├── run_dag.py
│       │   ├── solver_dag.py
│       │   └── types.py
│       ├── navigation/
│       │   ├── __init__.py
│       │   ├── data/
│       │   │   └── cgn_croisieres/
│       │   │       ├── all.csv
│       │   │       ├── lavaux_haut_lac.csv
│       │   │       ├── lavaux_haut_lac_grand_lac.csv
│       │   │       ├── petit_lac_grand_lac.csv
│       │   │       ├── translemanique.csv
│       │   │       └── ...
│       │   ├── cruise_model.py
│       │   └── ...
│       └── vessel_model/
│           ├── __init__.py
│           ├── config.py
│           ├── adapters.py
│           ├── vessel.py
│           └── ...
└── tests/
```

---
