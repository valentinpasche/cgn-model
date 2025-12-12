# cgn_model/vessel_model/storage.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray
from .config import StorageCfg, VectorSpec, VectorByPCIperLitre, VectorByLHVmass

type FArray = NDArray[np.floating]

@dataclass
class StorageResult:
    id: str
    bus: str
    tally: str
    # séries (facultatif d’exposer tout)
    power_selected_W: FArray          # max(0,P) ou -min(0,P)
    energy_kWh_series: FArray         # pas à pas
    energy_kWh_cum: FArray            # cumul
    # agrégats
    total_kWh: float
    # conversions optionnelles
    volume_m3: float | None
    mass_kg: float | None

def _select_power_slice(p_bus: FArray, tally: str) -> FArray:
    if tally == "consume":
        # conso = partie négative, retournée positive
        return np.clip(-p_bus, 0.0, None)
    elif tally == "inject":
        return np.clip(p_bus, 0.0, None)
    else:
        raise ValueError(f"tally inconnu: {tally!r}")

def _kWh_from_W_series(p_W: FArray, dt: float) -> FArray:
    # énergie par pas (Wh) = W * s / 3600 ; en kWh -> diviser par 3600*1000 = 3.6e6
    # plus simple: J = W*s ; kWh = J / 3.6e6
    J = p_W * float(dt)
    return J / 3.6e6

def _convert_energy(total_kWh: float, vector: VectorSpec | None) -> tuple[float | None, float | None]:
    if vector is None:
        return None, None

    if isinstance(vector, VectorByPCIperLitre):
        # kWh/L -> kWh/m3
        kWh_per_m3 = vector.pci_kWh_per_litre * 1000.0
        volume_m3 = total_kWh / kWh_per_m3
        mass_kg = None
        if vector.density_kg_per_m3:
            mass_kg = volume_m3 * float(vector.density_kg_per_m3)
        return volume_m3, mass_kg

    if isinstance(vector, VectorByLHVmass):
        # lhv en MJ/kg -> kWh/kg
        kWh_per_kg = (vector.lhv_MJ_per_kg * 1e6) / 3.6e6  # MJ/kg -> J/kg -> kWh/kg
        mass_kg = total_kWh / kWh_per_kg
        volume_m3 = None
        if vector.density_kg_per_m3:
            volume_m3 = mass_kg / float(vector.density_kg_per_m3)
        return volume_m3, mass_kg

    raise NotImplementedError(type(vector).__name__)

def compute_storage_from_bus(
    *,
    storage: StorageCfg,
    bus_power_W: FArray,
    dt: float,
) -> StorageResult:
    sel = _select_power_slice(bus_power_W, storage.tally)           # W ≥ 0
    e_series_kWh = _kWh_from_W_series(sel, dt)
    e_cum = np.cumsum(e_series_kWh)
    total = float(e_cum[-1]) if e_cum.size else 0.0
    vol, mass = _convert_energy(total, storage.vector)
    return StorageResult(
        id=storage.id,
        bus=storage.bus,
        tally=storage.tally,
        power_selected_W=sel,
        energy_kWh_series=e_series_kWh,
        energy_kWh_cum=e_cum,
        total_kWh=total,
        volume_m3=vol,
        mass_kg=mass,
    )
