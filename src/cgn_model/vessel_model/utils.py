# cgn_model/vessel_model/utils.py

from __future__ import annotations

from typing import Literal

# --- Définition des types d'unités pour Storage ---
# Massiques : Énergie par masse (Solides / Liquides)
type PCI_Massic_Unit = Literal["kWh/kg", "MJ/kg", "kJ/kg", "J/kg"]

# Volumiques : Énergie par volume (Liquides / Gaz)
type PCI_Volumic_Unit = Literal["kWh/l", "kWh/m3", "MJ/m3", "kJ/m3", "J/m3"]
type StorageLevelUnit = Literal[
    "J", "kJ", "MJ", "Wh", "kWh", "MWh",
    "kg", "t",
    "m3", "l",
]


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
    """
    Convertit un PCI massique vers J/kg.

    Parameters
    ----------
    value : float
        Valeur du PCI massique.
    unit : PCI_Massic_Unit
        Unite de `value` (`J/kg`, `kJ/kg`, `MJ/kg` ou `kWh/kg`).

    Returns
    -------
    float
        PCI en J/kg.
    """
    factor = _MASSIC_TO_J_PER_KG[str(unit)]
    out = float(value) * factor
    if out <= 0:
        raise ValueError("pci_to_j_per_kg: PCI doit etre > 0.")
    return out


def pci_to_j_per_m3(value: float, unit: PCI_Volumic_Unit) -> float:
    """
    Convertit un PCI volumique vers J/m3.

    Parameters
    ----------
    value : float
        Valeur du PCI volumique.
    unit : PCI_Volumic_Unit
        Unite de `value` (`J/m3`, `kJ/m3`, `MJ/m3`, `kWh/m3` ou `kWh/l`).

    Returns
    -------
    float
        PCI en J/m3.
    """
    factor = _VOLUMIC_TO_J_PER_M3[str(unit)]
    out = float(value) * factor
    if out <= 0:
        raise ValueError("pci_to_j_per_m3: PCI doit etre > 0.")
    return out


def energy_to_j(value: float, unit: StorageLevelUnit) -> float:
    """
    Convertit une énergie en Joules.

    Parameters
    ----------
    value : float
        Valeur energetique.
    unit : StorageLevelUnit
        Unite energetique (`J`, `kJ`, `MJ`, `Wh`, `kWh`, `MWh`).

    Returns
    -------
    float
        Energie en J.
    """
    factors = {
        "J": 1.0,
        "kJ": 1_000.0,
        "MJ": 1_000_000.0,
        "Wh": 3_600.0,
        "kWh": 3_600_000.0,
        "MWh": 3_600_000_000.0,
    }
    key = str(unit)
    if key not in factors:
        raise ValueError(f"energy_to_j: unité non énergétique: {unit!r}")
    return float(value) * factors[key]


def level_to_j(
    *,
    value: float,
    unit: StorageLevelUnit,
    pci_j_per_kg: float | None = None,
    pci_j_per_m3: float | None = None,
    density_kg_m3: float | None = None,
) -> float:
    """
    Convertit un niveau initial (énergie/masse/volume) vers Joules.

    Parameters
    ----------
    value : float
        Niveau initial a convertir.
    unit : StorageLevelUnit
        Unite de `value` : energie, masse (`kg`, `t`) ou volume (`m3`, `l`).
    pci_j_per_kg : float | None, optional
        PCI massique [J/kg].
    pci_j_per_m3 : float | None, optional
        PCI volumique [J/m3].
    density_kg_m3 : float | None, optional
        Densite [kg/m3] pour convertir masse et volume.

    Returns
    -------
    float
        Niveau initial equivalent en J.

    Notes
    -----
    - unite energie: conversion directe;
    - masse (kg/t): necessite pci_j_per_kg, ou pci_j_per_m3 + density;
    - volume (m3/l): necessite pci_j_per_m3, ou pci_j_per_kg + density.
    """
    v = float(value)
    u = str(unit)
    if v < 0:
        raise ValueError("level_to_j: la valeur initiale doit être >= 0.")

    if u in {"J", "kJ", "MJ", "Wh", "kWh", "MWh"}:
        return energy_to_j(v, unit)

    if u in {"kg", "t"}:
        m_kg = v if u == "kg" else v * 1_000.0
        if pci_j_per_kg is not None:
            return m_kg * float(pci_j_per_kg)
        if pci_j_per_m3 is not None and density_kg_m3 is not None and float(density_kg_m3) > 0:
            v_m3 = m_kg / float(density_kg_m3)
            return v_m3 * float(pci_j_per_m3)
        raise ValueError("level_to_j: unité masse fournie mais PCI/densité insuffisants.")

    if u in {"m3", "l"}:
        v_m3 = v if u == "m3" else v / 1_000.0
        if pci_j_per_m3 is not None:
            return v_m3 * float(pci_j_per_m3)
        if pci_j_per_kg is not None and density_kg_m3 is not None and float(density_kg_m3) > 0:
            m_kg = v_m3 * float(density_kg_m3)
            return m_kg * float(pci_j_per_kg)
        raise ValueError("level_to_j: unité volume fournie mais PCI/densité insuffisants.")

    raise ValueError(f"level_to_j: unité non supportée: {unit!r}")
