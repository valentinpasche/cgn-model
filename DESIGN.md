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
├── docs/
│   └── forward_vs_inverse.md
├── environment.yml
├── examples/
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
│       └── vessel_model/
│           ├── __init__.py
│           └── base.py
└── tests/
```

---
