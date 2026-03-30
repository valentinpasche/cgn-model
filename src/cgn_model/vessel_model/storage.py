# cgn_model/vessel_model/storage.py

"""
Post-traitement generique des bus de stockage (tally energie/puissance).
"""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray
from cgn_model.vessel_model.utils import level_to_j, pci_to_j_per_kg, pci_to_j_per_m3

type FArray = NDArray[np.floating]

@dataclass
class StorageResult:
    """
    Tally générique pour un bus de stockage, sans hypothèse sur le vecteur.
    Produit des séries dérivées prêtes à l'emploi et une vue DataFrame.

    Conventions :
      - p_W      : puissance signée telle que sortie par le solver pour le bus.
      - p_pos_W  : partie positive de p_W (>= 0).
      - p_neg_W  : magnitude de la partie négative (-min(p_W, 0) >= 0).
      - e_cum_J  : intégrale signée de p_W (cumsum(p_W) * dt).
      - e_pos_J  : intégrale de p_pos_W.
      - e_neg_J  : intégrale de p_neg_W.
      - t_s      : temps en secondes (0..(N-1)) * dt.

    Remarques :
      - Pas de clip : on n'écrase aucune information au tally.
      - L'enrichissement “vector” (kg, m^3, SoC, etc.) se fera en post-traitement,
        en ajoutant des colonnes au DataFrame si un vecteur est choisi.
    """
    id: str
    bus: str
    dt: float

    t_s: FArray
    p_W: FArray
    p_pos_W: FArray
    p_neg_W: FArray
    e_cum_J: FArray
    e_pos_J: FArray
    e_neg_J: FArray
    e_stock_J: FArray
    initial_level_J: float = 0.0

    # Métadonnée optionnelle
    vector: str | None = None
    vector_params: dict[str, Any] | None = None
    m_dot_kg_per_s: FArray | None = None
    m_cum_kg: FArray | None = None
    v_dot_m3_per_s: FArray | None = None
    v_cum_m3: FArray | None = None
    v_dot_l_per_s: FArray | None = None
    v_cum_l: FArray | None = None
    e_stock_kWh: FArray | None = None
    m_stock_kg: FArray | None = None
    v_stock_m3: FArray | None = None
    v_stock_l: FArray | None = None

    @property
    def N(self) -> int:
        return int(self.p_W.shape[0])

    # ----- Nouveaux totaux nets (énergie) -----
    @property
    def total_J(self) -> float:
        """Énergie nette sur l'horizon (J) = e_cum_J[-1]."""
        return float(self.e_cum_J[-1]) if self.e_cum_J.size else 0.0

    @property
    def total_kWh(self) -> float:
        """Énergie nette sur l'horizon (kWh)."""
        return self.total_J / 3.6e6

    @classmethod
    def from_bus(
        cls,
        *,
        id: str,
        bus_id: str,
        bus_net_w: FArray,
        dt: float,
        vector: str | None = None,
        vector_params: dict[str, Any] | None = None,
        initial_level: dict[str, Any] | None = None,
    ) -> "StorageResult":
        """
        Construit le tally à partir du signal net_w d'un bus et du pas dt.
        """
        if dt <= 0:
            raise ValueError("dt doit être > 0")

        p = np.asarray(bus_net_w, dtype=np.float64).reshape(-1)
        N = p.shape[0]

        t_s      = np.arange(N, dtype=np.float64) * float(dt)
        p_pos_W  = np.clip(p, 0.0, None)
        p_neg_W  = np.clip(-p, 0.0, None)
        e_cum_J  = np.cumsum(p) * float(dt)
        e_pos_J  = np.cumsum(p_pos_W) * float(dt)
        e_neg_J  = np.cumsum(p_neg_W) * float(dt)
        initial_level_j = 0.0

        m_dot_kg_per_s: FArray | None = None
        m_cum_kg: FArray | None = None
        v_dot_m3_per_s: FArray | None = None
        v_cum_m3: FArray | None = None
        v_dot_l_per_s: FArray | None = None
        v_cum_l: FArray | None = None
        e_stock_kWh: FArray | None = None
        m_stock_kg: FArray | None = None
        v_stock_m3: FArray | None = None
        v_stock_l: FArray | None = None

        vp = vector_params if isinstance(vector_params, dict) else {}
        basis = vp.get("pci_basis")
        pci_value = vp.get("pci_value")
        density = vp.get("density_kg_m3")
        pci_mass_unit = vp.get("pci_mass_unit")
        pci_volume_unit = vp.get("pci_volume_unit")
        pci_j_per_kg: float | None = None
        pci_j_per_m3: float | None = None

        if basis == "mass" and pci_value is not None and pci_mass_unit is not None:
            pci_j_per_kg = pci_to_j_per_kg(float(pci_value), str(pci_mass_unit))
            m_dot_kg_per_s = p / pci_j_per_kg
            m_cum_kg = np.cumsum(m_dot_kg_per_s) * float(dt)

            if density is not None and float(density) > 0:
                v_dot_m3_per_s = m_dot_kg_per_s / float(density)
                v_cum_m3 = np.cumsum(v_dot_m3_per_s) * float(dt)
                v_dot_l_per_s = v_dot_m3_per_s * 1_000.0
                v_cum_l = v_cum_m3 * 1_000.0

        elif basis == "volume" and pci_value is not None and pci_volume_unit is not None:
            pci_j_per_m3 = pci_to_j_per_m3(float(pci_value), str(pci_volume_unit))
            v_dot_m3_per_s = p / pci_j_per_m3
            v_cum_m3 = np.cumsum(v_dot_m3_per_s) * float(dt)
            v_dot_l_per_s = v_dot_m3_per_s * 1_000.0
            v_cum_l = v_cum_m3 * 1_000.0

            if density is not None and float(density) > 0:
                m_dot_kg_per_s = v_dot_m3_per_s * float(density)
                m_cum_kg = np.cumsum(m_dot_kg_per_s) * float(dt)

        if isinstance(initial_level, dict):
            raw_value = initial_level.get("value")
            raw_unit = initial_level.get("unit")
            if raw_value is not None and raw_unit is not None:
                initial_level_j = level_to_j(
                    value=float(raw_value),
                    unit=str(raw_unit),  # type: ignore[arg-type]
                    pci_j_per_kg=pci_j_per_kg,
                    pci_j_per_m3=pci_j_per_m3,
                    density_kg_m3=float(density) if density is not None else None,
                )

        e_stock_J = initial_level_j + e_cum_J
        e_stock_kWh = e_stock_J / 3_600_000.0
        if pci_j_per_kg is not None:
            m_stock_kg = e_stock_J / pci_j_per_kg
        elif pci_j_per_m3 is not None and density is not None and float(density) > 0:
            v_tmp = e_stock_J / pci_j_per_m3
            m_stock_kg = v_tmp * float(density)

        if pci_j_per_m3 is not None:
            v_stock_m3 = e_stock_J / pci_j_per_m3
            v_stock_l = v_stock_m3 * 1_000.0
        elif pci_j_per_kg is not None and density is not None and float(density) > 0:
            m_tmp = e_stock_J / pci_j_per_kg
            v_stock_m3 = m_tmp / float(density)
            v_stock_l = v_stock_m3 * 1_000.0

        return cls(
            id=id, bus=bus_id, dt=float(dt),
            t_s=t_s,
            p_W=p, p_pos_W=p_pos_W, p_neg_W=p_neg_W,
            e_cum_J=e_cum_J, e_pos_J=e_pos_J, e_neg_J=e_neg_J,
            e_stock_J=e_stock_J,
            initial_level_J=initial_level_j,
            vector=vector,
            vector_params=vector_params,
            m_dot_kg_per_s=m_dot_kg_per_s,
            m_cum_kg=m_cum_kg,
            v_dot_m3_per_s=v_dot_m3_per_s,
            v_cum_m3=v_cum_m3,
            v_dot_l_per_s=v_dot_l_per_s,
            v_cum_l=v_cum_l,
            e_stock_kWh=e_stock_kWh,
            m_stock_kg=m_stock_kg,
            v_stock_m3=v_stock_m3,
            v_stock_l=v_stock_l,
        )

    def to_dataframe(self):
        """
        Retourne un pandas.DataFrame avec les colonnes standardisées :
          - 't_s', 'p_W', 'p_pos_W', 'p_neg_W', 'e_cum_J', 'e_pos_J', 'e_neg_J'
        (Import local pour ne pas imposer pandas si non utilisé ailleurs.)
        """
        import pandas as pd  # type: ignore
        data: dict[str, FArray] = {
            "t_s": self.t_s,
            "p_W": self.p_W,
            "p_pos_W": self.p_pos_W,
            "p_neg_W": self.p_neg_W,
            "e_cum_J": self.e_cum_J,
            "e_pos_J": self.e_pos_J,
            "e_neg_J": self.e_neg_J,
            "e_stock_J": self.e_stock_J,
        }
        if self.e_stock_kWh is not None:
            data["e_stock_kWh"] = self.e_stock_kWh
        if self.m_dot_kg_per_s is not None:
            data["m_dot_kg_per_s"] = self.m_dot_kg_per_s
        if self.v_dot_m3_per_s is not None:
            data["v_dot_m3_per_s"] = self.v_dot_m3_per_s
        if self.v_dot_l_per_s is not None:
            data["v_dot_l_per_s"] = self.v_dot_l_per_s
        if self.m_stock_kg is not None:
            data["m_stock_kg"] = self.m_stock_kg
        if self.v_stock_m3 is not None:
            data["v_stock_m3"] = self.v_stock_m3
        if self.v_stock_l is not None:
            data["v_stock_l"] = self.v_stock_l
        return pd.DataFrame(data)

    # --- résumé structuré (dict) ---
    def summary_dict(self) -> dict[str, float]:
        """Stats clés prêtes à exporter/logguer."""
        total_inject_J  = float(self.e_pos_J[-1])    # énergie injectée (J)
        total_consume_J = float(self.e_neg_J[-1])    # énergie consommée (J, magnitude)
        net_J           = float(self.e_cum_J[-1])    # bilan signé (J)
    
        total_inject_kWh  = total_inject_J  / 3_600_000.0
        total_consume_kWh = total_consume_J / 3_600_000.0
        net_kWh           = net_J           / 3_600_000.0
    
        peak_inject_W  = float(np.max(self.p_pos_W))
        peak_consume_W = float(np.max(self.p_neg_W))
    
        return {
            "total_inject_J": total_inject_J,
            "total_consume_J": total_consume_J,
            "net_J": net_J,
            "total_inject_kWh": total_inject_kWh,
            "total_consume_kWh": total_consume_kWh,
            "net_kWh": net_kWh,
            "peak_inject_W": peak_inject_W,
            "peak_consume_W": peak_consume_W,
            "N": self.N,
            "dt": float(self.dt),
            "net_mass_kg": float(self.m_cum_kg[-1]) if self.m_cum_kg is not None else 0.0,
            "net_volume_m3": float(self.v_cum_m3[-1]) if self.v_cum_m3 is not None else 0.0,
            "net_volume_l": float(self.v_cum_l[-1]) if self.v_cum_l is not None else 0.0,
            "initial_level_kWh": float(self.initial_level_J) / 3_600_000.0,
            "final_level_kWh": float(self.e_stock_J[-1]) / 3_600_000.0 if self.e_stock_J.size else float(self.initial_level_J) / 3_600_000.0,
        }
    
    # --- propriété “jolie” (texte) ---
    @property
    def summary(self) -> str:
        """
        Texte multi-lignes prêt à afficher :
            print(res.summary)
        """
        s = self.summary_dict()
        head = f"Storage '{self.id}' on bus '{self.bus}' (N={s['N']}, dt={s['dt']:.3g}s)"
        body = [
            "Energy:",
            f"  + total inject : {s['total_inject_kWh']:.3f} kWh  ({s['total_inject_J']:,.0f} J)",
            f"  + total consume: {s['total_consume_kWh']:.3f} kWh  ({s['total_consume_J']:,.0f} J)",
            f"  + net          : {s['net_kWh']:.3f} kWh  ({s['net_J']:,.0f} J)",
            "Power peaks:",
            f"  + peak inject : {s['peak_inject_W']:,.0f} W",
            f"  + peak consume: {s['peak_consume_W']:,.0f} W",
        ]
        full = head + "\n" + "\n".join(body)
        print(full)


# --------------------------- Test ---------------------------
if __name__ == "__main__":
    
    id = "test_storage"
    bus = "generic"
    dt = 1.0 # [s]    
    net_w = np.array([0,1,2,3,3,3,4,5,2,1,0,1,2,3])*1e6 # [W]
    
    stor = StorageResult.from_bus(id=id, bus_id=bus, bus_net_w=net_w, dt=dt)
    
    dct = stor.summary_dict()
    df = stor.to_dataframe()
    
    stor.summary
    
    print(f"Total J : {stor.total_J:,.0f}")
    print(f"Total kWh : {stor.total_kWh:,.3f}")
