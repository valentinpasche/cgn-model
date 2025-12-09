# cgn_model/navigation/cruise_model.py

from __future__ import annotations

from importlib import resources
from pathlib import Path
from dataclasses import dataclass
from collections.abc import Iterable
import warnings
import datetime as dt
import math
import numpy as np
import pandas as pd

__all__ = ["Etape", "Course", "Croisiere", "SpeedProfileParams"]


def format_profile_summary(profile: np.ndarray | None, values: bool = False) -> str:
    """
    Représentation compacte d'un profil numpy 1D pour les __repr__.

    Exemple :
      array([0.0, 0.0, 0.1, ..., 1.2, 0.8, 0.0],
            shape=(34800,), mean=0.45, max=1.23, nonzero=32.1%)
    """
    if profile is None:
        return "None"

    arr = np.asarray(profile).ravel()
    n = arr.size

    if values:
        # --- partie "contenu" tronquée ---
        if n == 0:
            inner = ""
        elif n <= 6:
            inner = ", ".join(str(round(x,2)) for x in arr)
        else:
            head = ", ".join(str(round(x,2)) for x in arr[:3])
            tail = ", ".join(str(round(x,2)) for x in arr[-3:])
            inner = f"{head}, ..., {tail}"
    else:
        # --- overide de inner pour avoir que les stats ---
        inner = "..."
    
    # --- stats simples ---
    mean = float(arr.mean())
    vmax = float(arr.max())
    # fraction de points non nuls (utile pour voir nav vs pause)
    nonzero_frac = float((arr != 0).mean()) if n > 0 else 0.0

    return (
        "array(["
        f"{inner}"
        "], "
        f"shape=({n},), "
        f"mean={mean:.3g}, "
        f"max={vmax:.3g}, "
        f"nonzero={nonzero_frac*100:.1f}%)"
        ")"
    )

def _cgn_croisiere_csv_path(filename: str) -> Path:
    # -> src/cgn_model/navigation/data/cgn_croisieres/<filename>
    return (
        resources.files("cgn_model.navigation")
        .joinpath("data", "cgn_croisieres", filename)
    )

@dataclass(slots=True)
class SpeedProfileParams:
    dt: float = 1.0                  # [s]
    acc: float = 0.04                # [m/s²]
    dec: float = 0.04                # [m/s²]
    v_croisiere: float = 7    # [m/s]
    v_moyenne_horaire: float | None = None  # [m/s], optionnel, e.g. `23 / 3.6`
    allow_delay: bool = True

@dataclass
class Etape:
    from_port: str
    to_port: str
    depart: dt.time  # ou pd.Timestamp (date générique, 01.01.1900)
    km: float
    minutes: float
    profile: np.ndarray = None
    retard: float | None = None   # retard cumulé après cette étape [s]

    @property
    def is_pause(self) -> bool:
        # Pause = pas de déplacement
        return self.km == 0

    @property
    def nav_minutes(self) -> float:
        """Minutes réellement en navigation (0 si pause)."""
        return 0.0 if self.is_pause else float(self.minutes)

    @property
    def pause_minutes(self) -> float:
        """Minutes à quai (0 si déplacement)."""
        return float(self.minutes) if self.is_pause else 0.0

    @property
    def arrival(self) -> dt.time:
        """Heure d'arrivée (naïve, même jour)."""
        base = dt.datetime.combine(dt.date(2000, 1, 1), self.depart)
        arr = base + dt.timedelta(minutes=float(self.minutes))
        return arr.time()

    def __repr__(self) -> str:
        profile_repr = format_profile_summary(self.profile, values=True)
        base = self._repr_without_profile()[:-1]
        base += f", profile={profile_repr})"
        return base

    def _repr_without_profile(self) -> str:
        return (
            "Etape("
            f"from_port={self.from_port!r}, "
            f"to_port={self.to_port!r}, "
            f"is_pause={self.is_pause!r}, "
            f"depart={self.depart!r}, "
            f"km={self.km!r}, "
            f"minutes={self.minutes!r})"
        )

    def to_pretty_str(self, indent: int = 0) -> str:
        pad = " " * indent
        # depart est un datetime.time chez toi
        t = self.depart.strftime("%H:%M") if hasattr(self.depart, "strftime") else self.depart
        
        if self.is_pause:
            return f"{pad}Pause {t} {self.from_port} -> {self.to_port} ({self.minutes:g} min)"
        else:
            return (
                f"{pad}- {t} {self.from_port} -> {self.to_port} "
                f"({self.minutes:g} min, {self.km:g} km)"
            )

    def speed_profile(
        self,
        params: SpeedProfileParams | None = None,
        n_dt_delay: int | None = None,
    ) -> tuple[np.ndarray, int | None]:
        """
        Retourne un profil de vitesse v(t) pour cette étape, discrétisé toutes dt secondes.

        - Unités SI : m, s, m/s.
        - Si l'étape est une pause (km == 0) → vecteur de zéros sur toute la durée.
        - Sinon :
          - on construit un profil MRUA (accélération, éventuellement plateau,
            décélération) qui parcourt la distance donnée, avec v_croisiere,
            acc et dec ;
          - on calcule le temps physique minimal T_phys ;
          - si l'horaire (minutes) est plus long → on ajoute des zéros au
            début et à la fin (accostage / embarquement) ;
          - si l'horaire est trop court :
              - allow_delay=False → ValueError
              - allow_delay=True  → on utilise T_phys, et donc on arrive en retard.
        """
        def _catch_n_delay(n_current: int, n_delay: int) -> tuple[int, int, int]:
            " Reprise du retard possible "
            if n_delay == 0:
                return (n_current, n_delay, 0)
            # Garder une pause de 1*dt, si pause = delay
            if n_current == n_delay:
                n_removed = n_delay - 1
                n_current -= n_removed
                n_delay -= n_removed
            # Tout rattraper dans cette pause
            elif n_current > n_delay:
                n_removed = n_delay
                n_current -= n_removed
                n_delay = 0
            # Pas assez de pause pour tout rattraper
            elif n_current < n_delay:
                n_removed = max(0, n_current % n_delay) - 1
                n_current -= n_removed
                n_delay -= n_removed
            else:
                raise ValueError("[DEV] Erreur dans l'execution, level=_catch_n_delay()")
            
            return (n_current, n_delay, n_removed)
        
        if params is None:
            params = SpeedProfileParams()
        if not isinstance(params, SpeedProfileParams):
            raise TypeError("La méthode prend en entrée une instance de `SpeedProfilParams`,"
                        "    defaut None et crée l'instance avec les paramètres par défaut."
            )
        
        dt = params.dt
        acc = params.acc
        dec = params.dec
        v_croisiere = params.v_croisiere
        v_moyenne_horaire = params.v_moyenne_horaire
        allow_delay = params.allow_delay
        
        if not allow_delay:
            n_current_delay = None
        elif isinstance(n_dt_delay, int) and n_dt_delay > 0:
            n_current_delay = n_dt_delay
        elif not n_dt_delay:
            n_current_delay = 0
        else:
            raise ValueError("[DEV] Erreur dans l'execution, level=Etape()")
        
        # 0) cas pause : que des zéros
        t_sched = float(self.minutes) * 60.0  # [s]
        if self.is_pause or self.km <= 0:
            n = max(0, int(round(t_sched / dt)))
            
            #) Reprise du retard possible
            if n_current_delay:
                n, n_current_delay, n_removed = _catch_n_delay(n, n_current_delay)
                if n_removed:
                    warnings.warn(
                        f"[Correction] Pause à {self.from_port} : "
                        f"{float(n_removed * dt):.1f} s ont été supprimées pour tenir l'horaire.",
                        RuntimeWarning,
                    )

            return np.zeros(n, dtype=float), n_current_delay
        
        # 1) données de base
        distance_m = float(self.km) * 1000.0  # [m]
        a = float(acc)
        d = float(dec)
        v_max = float(v_croisiere)

        # 2) distance nécessaire pour accel + decel à v_max
        d_acc_dec = v_max**2 / (2 * a) + v_max**2 / (2 * d)

        if distance_m >= d_acc_dec:
            # Cas trapézoïdal : on atteint v_croisiere
            t_a = v_max / a         # temps d'accélération
            t_d = v_max / d         # temps de décélération
            d_remain = distance_m - d_acc_dec
            t_c = d_remain / v_max  # temps à vitesse constante
            T_phys = t_a + t_c + t_d
            v_peak = v_max
        else:
            # Cas triangulaire : distance trop courte pour atteindre v_croisiere
            # On calcule la vitesse max atteignable v_peak.
            v_peak = math.sqrt(2 * distance_m / (1 / a + 1 / d))
            t_a = v_peak / a
            t_d = v_peak / d
            t_c = 0.0
            T_phys = t_a + t_d

        # 3) Comparaison avec l'horaire
        if T_phys <= t_sched:
            catch_delay = True
        else:
            # Horaire physiquement impossible avec ces paramètres
            if not allow_delay:
                raise ValueError(
                    f"Horaire impossible sur {self.from_port} -> {self.to_port} : "
                    f"temps physique minimal {T_phys:.1f}s (v moyenne nav "
                    f"{distance_m / T_phys * 3.6:.1f} km/h) > temps d'horaire {t_sched:.1f}s"
                )
            else:
                catch_delay = False
                delay = T_phys - t_sched
                self.retard = delay
                new_n_delay = int(round(delay / dt))
                n_current_delay += new_n_delay
                warnings.warn(
                    f"[Retard] {self.from_port} -> {self.to_port} : "
                    f"il manque {delay:.1f} s pour tenir l'horaire.",
                    RuntimeWarning,
                )

        # Temps total du profil (incluant éventuellement le retard)
        if t_sched >= T_phys:
            slack = t_sched - T_phys
            slack_before = slack / 2.0
            slack_after = slack - slack_before  # gère les petites erreurs d'arrondi
        else:
            # on arrive en retard : tout le temps est du mouvement
            slack_before = 0.0
            slack_after = 0.0

        # 4) Discrétisation du profil de nav (sans les zéros)
        T_nav = T_phys
        n_nav = max(1, int(round(T_nav / dt)))
        t = np.linspace(0.0, T_nav, n_nav, endpoint=False)
        v = np.zeros_like(t)

        for i, ti in enumerate(t):
            if ti < t_a:
                v[i] = a * ti
            elif ti < t_a + t_c:
                v[i] = v_peak
            else:
                tau = ti - (t_a + t_c)
                v[i] = max(v_peak - d * tau, 0.0)

        # 5) On ajoute les périodes à vitesse nulle au début et à la fin
        n_before = int(round(slack_before / dt))
        n_after = int(round(slack_after / dt))
        
        #) Reprise du retard possible
        if catch_delay and n_current_delay:
            n_before, n_current_delay, n_removed_b = _catch_n_delay(n_before, n_current_delay)
            n_after, n_current_delay, n_removed_a = _catch_n_delay(n_after, n_current_delay)
            n_removed = n_removed_b + n_removed_a
            if n_removed:
                warnings.warn(
                    f"[Correction] Sur {self.from_port} -> {self.to_port} : "
                    f"{float(n_removed * dt):.1f} s ont été supprimées pour tenir l'horaire.",
                    RuntimeWarning,
                )
        
        if n_before > 0:
            v = np.concatenate([np.zeros(n_before, dtype=float), v])
        if n_after > 0:
            v = np.concatenate([v, np.zeros(n_after, dtype=float)])
        if v[0] != 0:
            v[0] = 0
        if v[-1] != 0:
            v[-1] = 0

        # 6) Optionnel : contrôle vs v_moyenne_horaire
        if v_moyenne_horaire is not None and T_phys > 0:
            v_nav = distance_m / T_phys  # [m/s]
            # si tu veux, tu peux mettre un warning si on est trop loin
            # du paramètre "macro" v_moyenne_horaire.
            # Exemple (tolérance 20%) :
            ratio = abs(v_nav - v_moyenne_horaire) / v_moyenne_horaire
            if ratio > 0.2:
                warnings.warn(
                    f"Vitesse moyenne nav effective {v_nav*3.6:.1f} km/h "
                    f"loin de la cible {v_moyenne_horaire*3.6:.1f} km/h "
                    f"sur {self.from_port} -> {self.to_port}.",
                    RuntimeWarning,
                )
        
        self.profile = v
        return self.profile, n_current_delay

@dataclass
class Course:
    numero: int
    etapes: list[Etape]
    profile: np.ndarray | None = None
    retard: float | None = None   # retard cumulé final [s]

    @property
    def from_port(self) -> str:
        return self.etapes[0].from_port

    @property
    def to_port(self) -> str:
        return self.etapes[-1].to_port

    @property
    def depart(self) -> dt.time:
        return self.etapes[0].depart

    @property
    def arrival(self) -> dt.time:
        return self.etapes[-1].arrival

    @property
    def total_km(self) -> float:
        return float(sum(e.km for e in self.etapes))

    @property
    def total_minutes(self) -> float:
        return float(sum(e.minutes for e in self.etapes))

    @property
    def nav_minutes(self) -> float:
        return float(sum(e.nav_minutes for e in self.etapes))

    @property
    def pause_minutes(self) -> float:
        return float(sum(e.pause_minutes for e in self.etapes))

    @property
    def avg_speed_kmh(self) -> float:
        """Vitesse moyenne en km/h (uniquement pendant navigation)."""
        if self.nav_minutes == 0:
            return 0.0
        return self.total_km / (self.nav_minutes / 60.0)

    def __repr__(self) -> str:
        if not self.etapes:
            return f"Course(numero={self.numero!r}, etapes=[])"
        
        profile_repr = format_profile_summary(self.profile, values=False)
        etapes_repr = ",\n            ".join(
            e._repr_without_profile() for e in self.etapes
        )
        return (
            "Course("
            f"numero={self.numero!r}, "
            f"from_port={self.from_port!r}, "
            f"to_port={self.to_port!r}, "
            f"n_etapes={len(self.etapes)}, "
            f"profile={profile_repr}), "
            "etapes=[\n"
            f"            {etapes_repr}\n"
            "        ])"
        )

    def to_pretty_str(self, indent: int = 0) -> str:
        pad = " " * indent
        lines = [f"{pad}Course {self.numero} {self.from_port} -> {self.to_port}"]
        for e in self.etapes:
            lines.append(e.to_pretty_str(indent=indent + 4))
        return "\n".join(lines)

    def speed_profile(
            self,
            params: SpeedProfileParams | None = None,
            n_dt_delay: int | None = None,
    ) -> tuple[np.ndarray, int | None]:
        """
        Construit et stocke le profil de vitesse de la course en concaténant
        les profils de toutes ses étapes (y compris pauses internes).
        
        Les kwargs sont passés tels quels à Etape.speed_profile, donc les
        valeurs par défaut ne sont définies qu'à un seul endroit.
        """
        if params is None:
            params = SpeedProfileParams()
        if not isinstance(params, SpeedProfileParams):
            raise TypeError("La méthode prend en entrée une instance de `SpeedProfilParams`,"
                        "    defaut None et crée l'instance avec les paramètres par défaut."
            )
        
        profiles: list[np.ndarray] = []
        
        if not params.allow_delay:
            n_current_delay = None
        elif isinstance(n_dt_delay, int) and n_dt_delay > 0:
            n_current_delay = n_dt_delay
        elif not n_dt_delay:
            n_current_delay = 0
        else:
            raise ValueError("[DEV] Erreur dans l'execution, level=Course()")
        
        for etape in self.etapes:
            v, n_current_delay = etape.speed_profile(params=params, n_dt_delay=n_current_delay)
            profiles.append(v)

        if profiles:
            self.profile = np.concatenate(profiles)
        else:
            self.profile = np.zeros(0, dtype=float)
            
        if n_current_delay:
            self.retard = n_current_delay * params.dt           
            warnings.warn(
                f"[Retard] Course {self.numero} : "
                f"il manque {self.retard} s pour tenir l'horaire.",
                RuntimeWarning,
            )
            
        return self.profile, n_current_delay

@dataclass
class Croisiere:
    nom: str
    courses: list[Course]
    pauses: list[Etape] # pauses entre les courses (km == 0 et changement de n° de course)
    profile: np.ndarray | None = None
    retard: float | None = None   # somme des retards des courses [s]

    @property
    def from_port(self) -> str:
        return self.courses[0].from_port

    @property
    def to_port(self) -> str:
        return self.courses[-1].to_port

    @property
    def trajet(self) -> list[Course | Etape]:
        """
        Séquence chronologique mixte : Course, pause (Etape), Course, ...
        Sans duplication d'objets, on retourne juste des références à
        self.courses et self.pauses.
        """
        def start_time_course(c: Course):
            return c.etapes[0].depart
        
        def start_time_pause(e: Etape):
            return e.depart
        
        courses = sorted(self.courses, key=start_time_course)
        pauses = sorted(self.pauses, key=start_time_pause)
        
        trajet: list[Course | Etape] = []
        
        i = j = 0
        while i < len(courses) and j < len(pauses):
            if start_time_course(courses[i]) <= start_time_pause(pauses[j]):
                trajet.append(courses[i])
                i += 1
            else:
                trajet.append(pauses[j])
                j += 1
        
        trajet.extend(courses[i:])
        trajet.extend(pauses[j:])
        return trajet

    @property
    def all_etapes(self) -> list[Etape]:
        """
        Toutes les étapes dans l'ordre chronologique :
        - toutes les étapes des courses
        - les pauses entre courses
        """
        etapes: list[Etape] = []
        for segment in self.trajet:
            if isinstance(segment, Course):
                etapes.extend(segment.etapes)
            else:  # pause entre courses
                etapes.append(segment)
        return etapes

    @property
    def total_km(self) -> float:
        return float(sum(e.km for e in self.all_etapes))

    @property
    def total_minutes(self) -> float:
        return float(sum(e.minutes for e in self.all_etapes))

    @property
    def nav_minutes(self) -> float:
        return float(sum(e.nav_minutes for e in self.all_etapes))

    @property
    def pause_minutes(self) -> float:
        return float(sum(e.pause_minutes for e in self.all_etapes))

    @property
    def avg_speed_kmh(self) -> float:
        if self.nav_minutes == 0:
            return 0.0
        return self.total_km / (self.nav_minutes / 60.0)
    
    def __repr__(self) -> str:
        # représentation "pythonique", structurelle
        traj = self.trajet
        profile_repr = format_profile_summary(self.profile, values=False)

        if not traj:
            trajet_repr = ""
        else:
            inner_parts = []
            for seg in traj:
                if isinstance(seg, Course):
                    inner_parts.append(repr(seg))
                else:  # Etape de pause entre courses
                    inner_parts.append(seg._repr_without_profile())
            inner = ",\n    ".join(inner_parts)
            trajet_repr = f"\n    {inner}\n"

        return (
            "Croisiere("
            f"nom={self.nom!r}, "
            f"from_port={self.from_port!r}, "
            f"to_port={self.to_port!r}, "
            f"profile={profile_repr}), "
            f"trajet=[{trajet_repr}])"
        )

    def __str__(self) -> str:
        # affichage "humain" quand tu fais print(croisiere)
        return self.to_pretty_str()

    def to_pretty_str(self) -> str:
        lines: list[str] = [
            f'Croisière "{self.nom}" {self.from_port} -> {self.to_port}',
        ]

        for segment in self.trajet:
            if isinstance(segment, Course):
                lines.append(segment.to_pretty_str(indent=2))
            else:  # pause = Etape
                lines.append(segment.to_pretty_str(indent=2))

        return "\n".join(lines)

    @staticmethod
    def view_croisiere(obj: Croisiere | Iterable[Croisiere]) -> None:
        """Visualisation d'une ou plusieurs croisières dans la console."""
        if isinstance(obj, Croisiere):
            croisieres = [obj]
        else:
            croisieres = list(obj)

        for c in croisieres:
            if not isinstance(c, Croisiere):
                continue
            print()
            print(c.to_pretty_str())
            print()

    # --- Construction à partir d'un DataFrame ---
    @classmethod
    def from_df(cls, df: pd.DataFrame) -> list[Croisiere]:
        df = df.copy()

        # Compléter croisiere / course vers le bas
        df["croisiere"] = df["croisiere"].ffill()
        df["course"] = df["course"].ffill()

        croisieres: list[Croisiere] = []

        # Un objet Croisiere par valeur de "croisiere"
        for croisiere_nom, df_croi in df.groupby("croisiere", sort=False):
            df_croi = df_croi.reset_index(drop=True)

            courses_map: dict[int, list[Etape]] = {}
            pauses: list[Etape] = []

            # On crée des étapes entre ligne i et i+1
            for i in range(len(df_croi) - 1):
                row_i = df_croi.iloc[i]
                row_j = df_croi.iloc[i + 1]

                # Si pas de km/minutes, on considère qu'il n'y a pas de segment
                if pd.isna(row_i.km) or pd.isna(row_i.minutes):
                    continue
                
                # Ignorer les pauses instantanées entre deux courses
                if (
                    float(row_i.km) == 0
                    and float(row_i.minutes) == 0
                    and int(row_i.course) != int(row_j.course)
                ):
                    continue
                
                etape = Etape(
                    from_port=row_i.port,
                    to_port=row_j.port,
                    depart=row_i.horaire,
                    km=float(row_i.km),
                    minutes=float(row_i.minutes),
                )

                course_i = int(row_i.course)
                course_j = int(row_j.course)

                # Pause entre deux courses (0 km + changement de n° de course)
                if etape.is_pause and course_i != course_j:
                    pauses.append(etape)
                else:
                    courses_map.setdefault(course_i, []).append(etape)

            # Construire les Course dans l'ordre chronologique
            courses = sorted(
                (
                    Course(numero=num, etapes=etapes)
                    for num, etapes in courses_map.items()
                ),
                key=lambda c: c.etapes[0].depart,
            )

            croisieres.append(cls(nom=croisiere_nom, courses=courses, pauses=pauses))

        return croisieres

    # --- Variante pratique: directement depuis le CSV ---
    @classmethod
    def from_csv(cls, path: str, sep: str = ";") -> list[Croisiere]:
        df = pd.read_csv(path, sep=sep)
        # Supprimer les lignes entièrement vides (toutes colonnes NA)
        df = df.dropna(how="all")

        # Parser la colonne "horaire" si ce n'est pas déjà fait
        if df["horaire"].dtype == object:
            df["horaire"] = pd.to_datetime(df["horaire"].str.strip(), format="%Hh%M")
            df["horaire"] = df["horaire"].dt.time

        return cls.from_df(df)

    # --- Variante a utiliser à l'intérieur du model CGN ---
    @classmethod
    def from_cgn_croisiere_csv(cls, name: str) -> list[Croisiere]:
        """
        name: "translemanique", "lavaux_haut_lac", etc.
        fichiers inclus dans le modèle sous :
        "src/cgn_model/navigation/data/cgn_croisieres/<filename>"
        """
        path = _cgn_croisiere_csv_path(f"{name}.csv")
        return cls.from_csv(path)

    def check_continuite(self) -> bool:
        """
        Vérifie que pour tout élément consécutif du trajet,
        le to_port du précédent == from_port du suivant.
        """
        t = self.trajet
        for prev, cur in zip(t, t[1:]):
            if prev.to_port != cur.from_port:
                return False
        return True

    def speed_profile(
            self,
            params: SpeedProfileParams | None = None,
    ) -> tuple[np.ndarray, int | None]:
        """
        Construit et stocke le profil complet de la croisière, en concaténant :
        - le profil de chaque Course
        - le profil des pauses (Etape) entre courses.

        Les kwargs sont passés tels quels à Course.speed_profile / Etape.speed_profile.
        """
        if params is None:
            params = SpeedProfileParams()
        if not isinstance(params, SpeedProfileParams):
            raise TypeError("La méthode prend en entrée une instance de `SpeedProfilParams`,"
                        "    defaut None et crée l'instance avec les paramètres par défaut."
            )
        
        segments_profiles: list[np.ndarray] = []
        
        if not params.allow_delay:
            n_current_delay = None
        else:
            n_current_delay = 0

        for seg in self.trajet:  # trajet = mix Course / Etape
            if isinstance(seg, Course):
                v, n_current_delay = seg.speed_profile(params=params, n_dt_delay=n_current_delay)
            else:  # Etape de pause entre courses
                v, n_current_delay = seg.speed_profile(params=params, n_dt_delay=n_current_delay)
            segments_profiles.append(v)

        if segments_profiles:
            self.profile = np.concatenate(segments_profiles)
        else:
            self.profile = np.zeros(0, dtype=float)

        if n_current_delay:
            self.retard = n_current_delay * params.dt
            warnings.warn(
                f"[Retard] Croisière {self.nom} : "
                f"il manque {self.retard} s pour tenir l'horaire.",
                RuntimeWarning,
            )

        return self.profile, n_current_delay


if __name__ == "__main__":
    
    # import matplotlib.pyplot as plt

    croisieres = Croisiere.from_cgn_croisiere_csv("all")
    
    # # ---- Test continuité + __repr__
    # for c in croisieres:
    #     assert c.check_continuite()
    #     print("======"*10)
    #     Croisiere.view_croisiere(c)
    
    # # ---- Test totaux croisières
    # c = croisieres[0]

    # print(c.nom)
    # print("Total km         :", c.total_km)
    # print("Temps total (min):", c.total_minutes)
    # print("Nav (min)        :", c.nav_minutes)
    # print("Pauses (min)     :", c.pause_minutes)
    # print("Vitesse moy (km/h):", c.avg_speed_kmh)
    