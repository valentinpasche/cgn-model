# -*- coding: utf-8 -*-

# Base de "cgn_model/navigation/cruise_model.py", identique initialement

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
import warnings
import datetime as dt
import math
import numpy as np
import pandas as pd


@dataclass(slots=True)
class SpeedProfileParams:
    dt: float = 1.0                  # [s]
    acc: float = 0.04                # [m/s²]
    dec: float = 0.04                # [m/s²]
    v_croisiere: float = 25 / 3.6    # [m/s]
    v_moyenne_horaire: float | None = 23 / 3.6  # [m/s], optionnel
    km_tml: bool = False
    allow_delay: bool = False

@dataclass
class Etape:
    from_port: str
    to_port: str
    depart: dt.time  # ou pd.Timestamp (date générique, 01.01.1900)
    km: float
    minutes: float
    profile: np.ndarray = None
    km_tlm: float = None

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

    def __repr__(self) -> str:
        return (
            "Etape("
            f"from_port={self.from_port!r}, "
            f"to_port={self.to_port!r}, "
            f"is_pause={self.is_pause!r}, "
            f"depart={self.depart!r}, "
            f"km={self.km!r}, "
            f"minutes={self.minutes!r})"
        )
    
    def add_km_tlm(self, tlm_dict: dict) -> Etape:
        if self.is_pause:
            self.km_tlm = float(0)
        else:
            for v in tlm_dict.values():
                if not v["port_1"] == self.from_port:
                    continue
                else:
                    if not v["port_2"] == self.to_port:
                        continue
                    else:
                        self.km_tlm = v["length"]
                        return

    def speed_profile(
        self,
        params: SpeedProfileParams | None = None,
    ) -> np.ndarray:
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
        if params is None:
            params = SpeedProfileParams()
        
        if not isinstance(params, SpeedProfileParams):
            raise TypeError("La méthode prend en entrée une instance de `SpeedProfilParams`,"
                        "    defaut None et crée l'instance avec les paramètres par défaut.")
        
        dt = params.dt
        acc = params.acc
        dec = params.dec
        v_croisiere = params.v_croisiere
        v_moyenne_horaire = params.v_moyenne_horaire
        allow_delay = params.allow_delay
        
        if params.km_tml:
            km = self.km_tlm
        else: km = self.km

        # 0) cas pause : que des zéros
        t_sched = float(self.minutes) * 60.0  # [s]
        if self.is_pause or km <= 0:
            n = max(0, int(round(t_sched / dt)))
            return np.zeros(n, dtype=float)

        # 1) données de base
        distance_m = float(km) * 1000.0  # [m]
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
        if t_sched < T_phys:
            # Horaire physiquement impossible avec ces paramètres
            if not allow_delay:
                raise ValueError(
                    f"Horaire impossible sur {self.from_port} -> {self.to_port} : "
                    f"temps physique minimal {T_phys:.1f}s (v moyenne nav "
                    f"{distance_m / T_phys * 3.6:.1f} km/h) > temps d'horaire {t_sched:.1f}s"
                )
            else:
                delay = T_phys - t_sched
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
        return self.profile

@dataclass
class Course:
    numero: int
    etapes: list[Etape]
    profile: np.ndarray | None = None

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
    
    def to_pretty_str(self, indent: int = 0) -> str:
        pad = " " * indent
        lines = [f"{pad}Course {self.numero} {self.from_port} -> {self.to_port}"]
        for e in self.etapes:
            lines.append(e.to_pretty_str(indent=indent + 4))
        return "\n".join(lines)

    def __repr__(self) -> str:
        if not self.etapes:
            return f"Course(numero={self.numero!r}, etapes=[])"

        etapes_repr = ",\n            ".join(repr(e) for e in self.etapes)
        return (
            "Course("
            f"numero={self.numero!r}, "
            f"from_port={self.from_port!r}, "
            f"to_port={self.to_port!r}, "
            "etapes=[\n"
            f"            {etapes_repr}\n"
            "        ])"
        )
    
    def add_km_tlm(self, tlm_dict: dict) -> Course:
        for etape in self.etapes:
            etape.add_km_tlm(tlm_dict)
        return
    
    def speed_profile(self, params: SpeedProfileParams | None = None) -> np.ndarray:
        """
        Construit et stocke le profil de vitesse de la course en concaténant
        les profils de toutes ses étapes (y compris pauses internes).
        
        Les kwargs sont passés tels quels à Etape.speed_profile, donc les
        valeurs par défaut ne sont définies qu'à un seul endroit.
        """
        profiles: list[np.ndarray] = []
        for etape in self.etapes:
            v = etape.speed_profile(params=params)
            profiles.append(v)

        if profiles:
            self.profile = np.concatenate(profiles)
        else:
            self.profile = np.zeros(0, dtype=float)

        return self.profile


@dataclass
class Croisiere:
    nom: str
    courses: list[Course]
    pauses: list[Etape] # pauses entre les courses (km == 0 et changement de n° de course)
    profile: np.ndarray | None = None

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
    
    def __repr__(self) -> str:
        # représentation "pythonique", structurelle
        traj = self.trajet

        if not traj:
            trajet_repr = ""
        else:
            inner = ",\n    ".join(repr(seg) for seg in traj)
            trajet_repr = f"\n    {inner}\n"

        return (
            "Croisiere("
            f"nom={self.nom!r}, "
            f"from_port={self.from_port!r}, "
            f"to_port={self.to_port!r}, "
            f"trajet=[{trajet_repr}])"
        )

    def __str__(self) -> str:
        # affichage "humain" quand tu fais print(croisiere)
        return self.to_pretty_str()
    
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

    def add_km_tlm(self, tlm_dict: dict) -> Croisiere:
        for seg in self.trajet:  # trajet = mix Course / Etape
            if isinstance(seg, Course):
                seg.add_km_tlm(tlm_dict)
            else:  # Etape de pause entre courses
                seg.add_km_tlm(tlm_dict)
        return

    def speed_profile(self, params: SpeedProfileParams | None = None) -> np.ndarray:
        """
        Construit et stocke le profil complet de la croisière, en concaténant :
        - le profil de chaque Course
        - le profil des pauses (Etape) entre courses.

        Les kwargs sont passés tels quels à Course.speed_profile / Etape.speed_profile.
        """
        segments_profiles: list[np.ndarray] = []

        for seg in self.trajet:  # trajet = mix Course / Etape
            if isinstance(seg, Course):
                v = seg.speed_profile(params=params)
            else:  # Etape de pause entre courses
                v = seg.speed_profile(params=params)
            segments_profiles.append(v)

        if segments_profiles:
            self.profile = np.concatenate(segments_profiles)
        else:
            self.profile = np.zeros(0, dtype=float)

        return self.profile


if __name__ == "__main__":
    
    # import matplotlib.pyplot as plt

    croisieres = Croisiere.from_csv("assets/croisieres/all.csv")
    
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
    
    # for course in c.courses:
    #     print(
    #         f"Course {course.numero}: {course.from_port} -> {course.to_port}, "
    #         f"{course.total_km} km, {course.nav_minutes} min nav, "
    #         f"vitesse moy {course.avg_speed_kmh:.1f} km/h"
    #     )
    
    
    # # ---- ALL - Vitesse moyenne
    # all_vm = []
    # for c in croisieres:
    #     for e in c.all_etapes:
    #         if e.is_pause:
    #             vm = 0
    #         else:
    #             vm = e.km / (e.minutes/60)
    #         all_vm.append(vm)
            
    # # ---- ALL - Calcul profile vitesse
    # default_params = SpeedProfileParams(allow_delay=True, v_moyenne_horaire=None)
    
    # e_profiles = []
    # for c in croisieres:
    #     for e in c.all_etapes:
    #         p = e.speed_profile(default_params)
    #         e_profiles.append(p)
            
    # c_profiles = []
    # for c in croisieres:
    #     p = c.speed_profile(default_params)
    #     c_profiles.append(p)
    # for i, p in enumerate(c_profiles):
    #     t = np.arange(0, len(p), 1)
    #     fig = plt.figure(i)
    #     plt.plot(t, p)
    
    # # ---- ALL - étapes OD
    # all_od = set()
    # for c in croisieres:
    #     for e in c.all_etapes:
    #         if e.is_pause:
    #             continue
    #         else:
    #             od = sorted([e.from_port, e.to_port])
    #             all_od.add((od[0], od[1]))
    
    # for od in all_od:
    #     o = od[0]
    #     d = od[1]
    #     print(f"{o};{d};tbd;")
    
    # ---- Ajout des km TLM (+OSM)
    # od = pd.read_csv("assets/croisieres/length_TLM_OSM.csv", sep=";")
    # do = od.copy().rename(columns={"port_1": "port_2", "port_2": "port_1"})
    # oddo = pd.concat([od, do]).reset_index(drop=True).to_dict("index")
     
    # for c in croisieres:
    #     c.add_km_tlm(oddo)
    
    # for c in croisieres:
    #     for e in c.all_etapes:
    #         if e.is_pause:
    #             continue
    #         else:
    #             print(f"{e.from_port} -> {e.to_port}")
    #             print("   km CGN | km TLM")
    #             print(f"     {round(e.km,1)} | {round(e.km_tlm,2)}")
    #             print()

    # ---- Calcul des profiles avec TLM
    # c_profiles_cgn = []
    # params_km_cgn = SpeedProfileParams(allow_delay=True, v_moyenne_horaire=None)
    # for c in croisieres:
    #     p = c.speed_profile(params_km_cgn)
    #     c_profiles_cgn.append(p)

    # c_profiles_tlm = []
    # params_km_tlm = SpeedProfileParams(allow_delay=True, v_moyenne_horaire=None, km_tml=True)
    # for c in croisieres:
    #     p = c.speed_profile(params_km_tlm)
    #     c_profiles_tlm.append(p)
    
    # for i, p_cgn in enumerate(c_profiles_cgn):
    #     p_tlm = c_profiles_tlm[i]
    #     t_max = max(len(p_cgn), len(p_tlm))
    #     t = np.arange(0, t_max, 1)
    #     p_cgn_pad = np.pad(p_cgn, (0, t_max - len(p_cgn)), mode="constant")
    #     p_tlm_pad = np.pad(p_tlm, (0, t_max - len(p_tlm)), mode="constant")
        
    #     fig = plt.figure(i)
    #     plt.plot(t, p_cgn_pad, label="CGN")
    #     plt.plot(t, p_tlm_pad, label="TLM")
    #     plt.legend()

        
            