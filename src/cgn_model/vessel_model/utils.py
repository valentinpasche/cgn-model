# cgn_model/vessel_model/utils.py

from __future__ import annotations

from typing import Literal

# --- Définition des types d'unités pour Storage ---
# Massiques : Énergie par masse (Solides / Liquides)
type PCI_Massic_Unit = Literal["kWh/kg", "MJ/kg", "kJ/kg", "J/kg"]

# Volumiques : Énergie par volume (Liquides / Gaz)
type PCI_Volumic_Unit = Literal["kWh/l", "kWh/m3", "MJ/m3", "kJ/m3", "J/m3"]


_MASSIC_TO_J_PER_KG: dict[str, float] = {
    "J/kg": 1.0,
    "kJ/kg": 1_000.0,
    "MJ/kg": 1_000_000.0,
    "kWh/kg": 3_600_000.0,
}

_VOLUMIC_TO_J_PER_M3: dict[str, float] = {
    "J/m3": 1.0,
    "kJ/m3": 1_000.0,
    "MJ/m3": 1_000_000.0,
    "kWh/m3": 3_600_000.0,
    "kWh/l": 3_600_000.0 * 1_000.0,  # 1 m3 = 1000 l
}


def pci_to_j_per_kg(value: float, unit: PCI_Massic_Unit) -> float:
    """Convertit un PCI massique vers J/kg."""
    factor = _MASSIC_TO_J_PER_KG[str(unit)]
    out = float(value) * factor
    if out <= 0:
        raise ValueError("pci_to_j_per_kg: PCI doit etre > 0.")
    return out


def pci_to_j_per_m3(value: float, unit: PCI_Volumic_Unit) -> float:
    """Convertit un PCI volumique vers J/m3."""
    factor = _VOLUMIC_TO_J_PER_M3[str(unit)]
    out = float(value) * factor
    if out <= 0:
        raise ValueError("pci_to_j_per_m3: PCI doit etre > 0.")
    return out
