# Configurations types

Ce dossier regroupe plusieurs configurations complètes illustrant différentes
architectures énergétiques :

| Fichier | Architecture représentée |
| --- | --- |
| `config_DE.yaml` | diesel-électrique avec rendement variable du groupe genset |
| `config_steam.yaml` | propulsion vapeur et production électrique auxiliaire |
| `config_full_elec.yaml` | propulsion électrique alimentée par batteries |
| `config_H2.yaml` | pile à combustible hydrogène |
| `config_from_UI.yaml` | exemple brut exporté par l'interface graphique |

Ces configurations servent d'exemples structurels. Les coefficients,
rendements, capacités et niveaux initiaux doivent être adaptés et validés avant
une utilisation métier.

## Exécuter les configurations

Le script `run.py` charge et exécute successivement toutes les configurations :

```text
python examples/configurations_type_260605/run.py
```

Pour utiliser une seule configuration depuis un autre script :

```python
from pathlib import Path

from cgn_model import Vessel

config_path = Path("examples/configurations_type_260605/config_DE.yaml")
yaml_text = config_path.read_text(encoding="utf-8")

vessel = Vessel.from_yaml(yaml_text)
vessel.run()
df = vessel.results_dataframe()
```

`config_from_UI.yaml` conserve volontairement la forme produite par l'interface,
notamment ses identifiants et ses valeurs numériques détaillées. Les autres
fichiers privilégient une écriture YAML plus lisible pour une utilisation
manuelle.
