# cgn_model/vessel_model/storage.py

"""
Post-traitement generique des bus de stockage (tally energie/puissance).
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray

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
      - L'enrichissement “vecteur” (kg, m^3, SoC, etc.) se fera en post-traitement,
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

    # Métadonnée optionnelle
    vecteur: str | None = None

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
        vecteur: str | None = None,
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

        return cls(
            id=id, bus=bus_id, dt=float(dt),
            t_s=t_s,
            p_W=p, p_pos_W=p_pos_W, p_neg_W=p_neg_W,
            e_cum_J=e_cum_J, e_pos_J=e_pos_J, e_neg_J=e_neg_J,
            vecteur=vecteur,
        )

    def to_dataframe(self):
        """
        Retourne un pandas.DataFrame avec les colonnes standardisées :
          - 't_s', 'p_W', 'p_pos_W', 'p_neg_W', 'e_cum_J', 'e_pos_J', 'e_neg_J'
        (Import local pour ne pas imposer pandas si non utilisé ailleurs.)
        """
        import pandas as pd  # type: ignore
        return pd.DataFrame(
            {
                "t_s":      self.t_s,
                "p_W":      self.p_W,
                "p_pos_W":  self.p_pos_W,
                "p_neg_W":  self.p_neg_W,
                "e_cum_J":  self.e_cum_J,
                "e_pos_J":  self.e_pos_J,
                "e_neg_J":  self.e_neg_J,
            }
        )

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

