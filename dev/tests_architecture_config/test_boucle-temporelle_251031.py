# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Literal, Dict, List, Optional, Tuple
import math

# ---------------------------
# Carriers & Protocols (API)
# ---------------------------

Carrier = Literal["Electrical", "Mechanical", "Thermal", "Chemical"]

class SupportsLoad(Protocol):
    """Protocol for a time-dependent power **load** published on a given energy carrier (bus).

    Units
    ------
    - Power returned by `power_demand` is **W** (SI).
    - Returned value must be **≥ 0** and represents how much power the load *requires* at time `t`.
    
    Contract
    --------
    - Attribute `carrier` declares the target bus carrier: one of
      {"Electrical", "Mechanical", "Thermal", "Chemical"}.
    - Method `power_demand(t)` returns the instantaneous demanded power in W at simulation time `t`.
    
    Notes
    -----
    - If you need a bidirectional “prosumer”, implement both `SupportsLoad` and `SupportsSource`
      on the same object; use positive supply in `SupportsSource` and positive demand here.
    """
    carrier: Carrier
    def power_demand(self, t: float) -> float: ...  # W (>=0 = demande)

class SupportsSource(Protocol):
    """Protocol for a time-dependent power **source** published on a given energy carrier (bus).
    
    Units
    ------
    - Power returned by `power_supply` is **W** (SI).
    - Returned value must be **≥ 0** and represents how much power the source *injects* at time `t`.
    
    Contract
    --------
    - Attribute `carrier` declares the target bus carrier: one of
      {"Electrical", "Mechanical", "Thermal", "Chemical"}.
    - Method `power_supply(t)` returns the instantaneous injected power in W at simulation time `t`.
    
    Notes
    -----
    - For a bidirectional “prosumer”, implement `SupportsLoad` as well and use the same `carrier`.
    """
    carrier: Carrier
    def power_supply(self, t: float) -> float: ...  # W (>=0 = injection)

class SupportsStorage(Protocol):
    """Protocol for an energy **storage** asset attached to a single bus (single carrier).
    
    Role
    ----
    Represents a storage that exchanges instantaneous power with a bus and maintains an
    internal energy state (in **J**), subject to charge/discharge limits.
    
    Units
    ------
    - Power arguments/returns are **W** (SI).
    - Energy state is **J** (SI).
    
    Contract
    --------
    - Attribute `carrier`: the bus carrier handled by this storage.
    - `limits() -> (P_discharge_max_W, P_charge_max_W)`: discharge(+)/charge(−) limits in W.
    - `state_joules() -> float`: current stored energy in J.
    - `apply(p_net_w, dt) -> float`:
        - If `p_net_w > 0`, request **discharge** of `p_net_w` W for duration `dt` seconds.
        - If `p_net_w < 0`, request **charge** of `|p_net_w|` W for duration `dt`.
        - Must return the **actual** signed power effectively exchanged (may be saturated).
          Convention: +W = discharge to the bus, −W = charge from the bus.
    
    Notes
    -----
    - Implement internal efficiency and ramp/thermal constraints inside `apply`.
    - For fuel tanks, store energy in J and convert to mass flow outside via PCI when needed.
    """
    carrier: Carrier
    def limits(self) -> Tuple[float, float]: ...    # (P_discharge_max_W, P_charge_max_W)
    def state_joules(self) -> float: ...           # énergie stockée [J]
    def apply(self, p_net_w: float, dt: float) -> float:
        """
        p_net_w > 0  => décharge (fournit au bus)
        p_net_w < 0  => charge (absorbe du bus)
        Retourne la puissance effectivement échangée (W), saturée par limites/état.
        """

class SupportsConverter(Protocol):
    """Protocol for an energy **converter** mapping one carrier to another (A → B).
    
    Role
    ----
    Consumes power on a **from_carrier** bus and injects power on a **to_carrier** bus,
    subject to limits and efficiency.
    
    Units
    ------
    - Input and output powers are **W** (SI).
    - Efficiencies are dimensionless (0..1), possibly varying with load.
    
    Contract
    --------
    - Attributes: `from_carrier`, `to_carrier` (each in {"Electrical","Mechanical","Thermal","Chemical"}).
    - `limits() -> (P_in_min_W, P_in_max_W)`: admissible input power range in W.
    - `efficiency(p_in_w) -> float`: conversion efficiency at the requested input power.
    - `apply(p_in_w) -> float`: request a conversion at input power `p_in_w` (clipped to limits),
      returns the resulting **output** power in W.
    
    Notes
    -----
    - The orchestrator (allocator) is responsible for placing the corresponding −W on the
      from-bus and +W on the to-bus using this converter’s response.
    """
    from_carrier: Carrier
    to_carrier: Carrier
    def limits(self) -> Tuple[float, float]: ...    # (P_in_min_W, P_in_max_W)
    def efficiency(self, p_in_w: float) -> float: ...
    def apply(self, p_in_w: float) -> float:
        """
        Pose la conversion A->B (W). Retourne P_out_W (peut être 0 si saturé).
        Convention: le converter "consomme" sur from_carrier et "injecte" sur to_carrier.
        """


# ---------------------------
# Bus & Allocator (logique)
# ---------------------------

@dataclass
class Bus:
    """Concrete **bus** for a given carrier (e.g. Electrical, Mechanical).
    
    Role
    ----
    Aggregates participants (loads, sources, storages, converters) and holds per-step
    bookkeeping for network balancing.
    
    Attributes
    ----------
    carrier : Literal["Electrical","Mechanical","Thermal","Chemical"]
        Carrier handled by this bus instance.
    bus_id : str
        Identifier of the bus instance (supports partitioned networks, e.g. "Thermal:steam_A").
    loads : list[SupportsLoad]
    sources : list[SupportsSource]
    converters_in : list[SupportsConverter]
        Converters that **consume** power from this bus (their `from_carrier` == `carrier`).
    converters_out : list[SupportsConverter]
        Converters that **inject** power into this bus (their `to_carrier` == `carrier`).
    storages : list[SupportsStorage]
    
    Per-step state
    --------------
    net_injection_W : float
        Sum of all injections minus demands (excluding storage), computed during balancing.
    storage_exchange_W : float
        Net storage contribution (+ discharge, − charge) decided during balancing.
    
    Methods
    -------
    reset_step()
        Clears per-step accumulators before the allocator runs.
    
    Notes
    -----
    - The allocator/network orchestration controls how converter I/O is routed across buses.
    """
    carrier: Carrier
    bus_id: str
    # registres dynamiques à chaque pas
    loads: List[SupportsLoad] = field(default_factory=list)
    sources: List[SupportsSource] = field(default_factory=list)
    converters_in: List[SupportsConverter] = field(default_factory=list)   # qui consomment sur ce bus
    converters_out: List[SupportsConverter] = field(default_factory=list)  # qui injectent vers ce bus
    storages: List[SupportsStorage] = field(default_factory=list)

    # état du pas courant (écrit par l'allocator)
    net_injection_W: float = 0.0  # somme des +W injectés -W demandés (hors stockage)
    storage_exchange_W: float = 0.0  # contribution nette des stockages (peut être + ou -)

    def reset_step(self):
        self.net_injection_W = 0.0
        self.storage_exchange_W = 0.0

@dataclass
class EnergyNetwork:
    """Energy network containing multiple buses + a simple greedy **allocator**.
    
    Role
    ----
    For each time step, evaluates demands and supplies on each bus, discharges storage
    to reduce deficits, and offers surplus to converters that consume on this bus.
    Returns a per-bus **slack** (W): positive slack = unmet demand, negative slack = surplus.
    
    Caveats (simplified demo)
    -------------------------
    - Converter outputs are not fully propagated to their destination buses here;
      a production orchestrator should coordinate both sides explicitly.
    - The allocator heuristic is intentionally simple to illustrate class interactions.
    
    Methods
    -------
    step_balance(t: float, dt: float) -> dict[str, float]
        Compute per-bus slack after sources, storage-discharge, and partial converter handling.
        Returns `{"BusID": slack_W, ...}`.
    
    Units
    -----
    - All powers are **W**; time step `dt` is **s**.
    """
    buses: Dict[str, Bus]  # key = bus_id

    def step_balance(self, t: float, dt: float) -> Dict[str, float]:
        """Retourne un dict slack[bus_id] (W) si charge non couverte (>0) ou surplus (<0)."""
        slacks = {}
        for bus_id, bus in self.buses.items():
            bus.reset_step()

            # 1) Loads (demande)
            d_total = sum(max(0.0, l.power_demand(t)) for l in bus.loads)

            # 2) Sources directes (injection)
            s_total = sum(max(0.0, s.power_supply(t)) for s in bus.sources)

            # 3) Converters OUT vers ce bus: on additionne seulement ce qui est déjà décidé ailleurs
            #    (dans ce squelette, on pilote les converters "depuis" leur from_bus, ci-dessous)
            #    donc ici, juste initialisation
            c_out_total = 0.0

            # 4) Premier coup de pouce: storages en décharge si besoin
            p_needed = max(0.0, d_total - s_total)
            p_storage_discharge = 0.0
            for st in bus.storages:
                p_dis_max, _ = st.limits()
                if p_needed <= 0: break
                p = min(p_dis_max, p_needed)
                actual = st.apply(+p, dt)  # +p => décharge (fournit au bus)
                p_storage_discharge += max(0.0, actual)
                p_needed -= max(0.0, actual)

            # 5) Converters qui consomment sur CE bus (from=bus.carrier)
            #    Ils peuvent prendre de l'énergie de ce bus pour alimenter un autre bus.
            #    Très simple: on leur donne ce qui reste en "surplus" pour alimenter l'aval.
            surplus = max(0.0, s_total + p_storage_discharge - d_total)
            for conv in bus.converters_in:
                p_in_min, p_in_max = conv.limits()
                if surplus <= 0: break
                p_in = min(surplus, max(0.0, p_in_max))
                p_out = conv.apply(p_in)  # publiera sur son bus de sortie par ailleurs
                surplus -= p_in
                # NB: ici on ne crédite pas le bus de sortie (ce serait proprement géré par un
                #     orchestrateur qui connaît les deux bus et route p_out vers le bon Bus).

            # 6) Si on est encore en déficit: on essaye de charger les converters OUT (qui injectent sur CE bus)
            #    Dans ce squelette, on les laissera “externes” (pilotés par l'autre bus).
            #    Donc pas d'action ici — on enregistre juste le slack.
            after_sources_storages = s_total + p_storage_discharge + c_out_total
            slack = d_total - after_sources_storages  # >0 = manque; <0 = surplus
            bus.net_injection_W = after_sources_storages - d_total
            bus.storage_exchange_W = p_storage_discharge  # net de ce pas
            slacks[bus_id] = slack
        return slacks


# ---------------------------
# Storage (technique)
# ---------------------------

@dataclass
class Battery:
    """Generic **battery** storage attached to the Electrical bus.
    
    Model
    -----
    - Fixed charge/discharge power limits.
    - Symmetric round-trip efficiency applied on energy transfers.
    - Energy state tracked in **J** (SI).
    
    Attributes
    ----------
    carrier : Literal["Electrical"]
    e_joules : float
        Current stored energy [J].
    p_discharge_max_w : float
    p_charge_max_w : float
    eta_roundtrip : float
        Round-trip efficiency (0..1).
    
    Methods
    -------
    limits() -> (float, float)
        Returns (P_discharge_max_W, P_charge_max_W).
    state_joules() -> float
        Current stored energy [J].
    apply(p_net_w: float, dt: float) -> float
        Request discharge (+W) or charge (−W) for duration `dt` [s].
        Returns the **actual** signed power exchanged (may be saturated).
    """
    carrier: Carrier = "Electrical"
    e_joules: float = 5e9                # énergie stockée
    p_discharge_max_w: float = 300e3
    p_charge_max_w: float = 200e3
    eta_roundtrip: float = 0.95          # simple : symétrique décharge/charge

    def limits(self) -> Tuple[float, float]:
        return (self.p_discharge_max_w, self.p_charge_max_w)

    def state_joules(self) -> float:
        return self.e_joules

    def apply(self, p_net_w: float, dt: float) -> float:
        # +p_net_w => décharge ; -p_net_w => charge
        if p_net_w > 0:  # décharge
            p = min(p_net_w, self.p_discharge_max_w)
            e = p * dt / self.eta_roundtrip
            e = min(e, self.e_joules)  # pas décharger sous zéro
            self.e_joules -= e
            actual_p = e * self.eta_roundtrip / dt
            return +actual_p
        elif p_net_w < 0:  # charge
            p = min(-p_net_w, self.p_charge_max_w)
            e = p * dt * self.eta_roundtrip
            self.e_joules += e
            actual_p = e / (self.eta_roundtrip * dt)
            return -actual_p
        return 0.0


# ---------------------------
# Converters (technique)
# ---------------------------

@dataclass
class PrimeMoverDE_Aggregate:
    """Aggregate **prime mover** (Electrical → Mechanical) with global efficiency.
    
    Use-case
    --------
    Represents Motor + Drive + Gear as a single equivalent efficiency.
    
    Attributes
    ----------
    from_carrier : "Electrical"
    to_carrier   : "Mechanical"
    eta_global   : float
        Constant overall efficiency (0..1).
    p_in_min_w, p_in_max_w : float
        Admissible electrical input power range [W].
    
    Methods
    -------
    limits() -> (float, float)
    efficiency(p_in_w: float) -> float
        Returns `eta_global`.
    apply(p_in_w: float) -> float
        Clips `p_in_w` to limits and returns `p_out_w = eta_global * p_in_w`.
    """
    from_carrier: Carrier = "Electrical"
    to_carrier: Carrier = "Mechanical"
    eta_global: float = 0.93 * 0.98 * 0.97
    p_in_min_w: float = 0.0
    p_in_max_w: float = 1.0e6

    def limits(self) -> Tuple[float, float]:
        return (self.p_in_min_w, self.p_in_max_w)

    def efficiency(self, p_in_w: float) -> float:
        return self.eta_global

    def apply(self, p_in_w: float) -> float:
        p_in = max(self.p_in_min_w, min(p_in_w, self.p_in_max_w))
        return p_in * self.efficiency(p_in)

@dataclass
class PrimeMoverDE_Detailed:
    """Simple “detailed” **prime mover** (Electrical → Mechanical) with load-dependent η.
    
    Use-case
    --------
    Very lightweight stand-in for a motor+drive+gear map: efficiency slightly varies
    with relative input load.
    
    Attributes
    ----------
    from_carrier : "Electrical"
    to_carrier   : "Mechanical"
    p_rated_w    : float
    eta_nominal  : float
    p_in_min_w, p_in_max_w : float
    
    Methods
    -------
    limits() -> (float, float)
    efficiency(p_in_w: float) -> float
        Returns an efficiency curve based on relative load p_in/p_rated, clipped to [0.5, 0.98].
    apply(p_in_w: float) -> float
        Clips input to limits and returns `p_out_w = η(p_in) * p_in`.
    """
    from_carrier: Carrier = "Electrical"
    to_carrier: Carrier = "Mechanical"
    p_rated_w: float = 800e3
    eta_nominal: float = 0.92
    p_in_min_w: float = 0.0
    p_in_max_w: float = 800e3

    def limits(self) -> Tuple[float, float]:
        return (self.p_in_min_w, self.p_in_max_w)

    def efficiency(self, p_in_w: float) -> float:
        x = max(0.0, min(1.0, p_in_w / max(1.0, self.p_rated_w)))
        # ex: légère cloche, pénalité à faibles charges
        eta = self.eta_nominal * (0.9 + 0.2 * x)   # 0.9η_nom à très faible charge, 1.1η_nom à Pn
        return max(0.5, min(eta, 0.98))

    def apply(self, p_in_w: float) -> float:
        p_in = max(self.p_in_min_w, min(p_in_w, self.p_in_max_w))
        return p_in * self.efficiency(p_in)


# ---------------------------
# OpsHub (entrées utilisateur)
# ---------------------------

@dataclass
class PropulsionDemand:
    """Aggregate **propulsion demand** map: ship speed → required shaft power.
    
    Role
    ----
    Provides a simple interpolation from speed `v` [m/s] to mechanical shaft power [W],
    to be published as a Mechanical load on the propulsion shaft bus.
    
    Attributes
    ----------
    map_v_to_pshaft : dict[float, float]
        Lookup table {speed_m_s: power_W}. Must be defined in SI units.
    
    Methods
    -------
    p_shaft(v: float) -> float
        Linear interpolation over the table. Values are clamped at the table range.
    """
    map_v_to_pshaft: Dict[float, float]  # table simple (m/s -> W)

    def p_shaft(self, v: float) -> float:
        # interpolation linéaire ultra simple (suppose table triée par v croissant)
        vs = sorted(self.map_v_to_pshaft.keys())
        if v <= vs[0]: return self.map_v_to_pshaft[vs[0]]
        if v >= vs[-1]: return self.map_v_to_pshaft[vs[-1]]
        # find bracket
        for i in range(len(vs)-1):
            if vs[i] <= v <= vs[i+1]:
                v0, v1 = vs[i], vs[i+1]
                p0, p1 = self.map_v_to_pshaft[v0], self.map_v_to_pshaft[v1]
                a = (v - v0) / (v1 - v0)
                return p0 + a * (p1 - p0)
        return 0.0

@dataclass
class MechanicalLoadFromPropulsion(SupportsLoad):
    """Mechanical **load** wrapper that uses a speed profile and PropulsionDemand.
    
    Role
    ----
    Exposes `power_demand(t)` [W] on the Mechanical bus by:
    1) sampling the speed `v(t)` from a provided time→speed profile,
    2) calling `PropulsionDemand.p_shaft(v)` to get shaft power.
    
    Attributes
    ----------
    carrier : "Mechanical"
    prop : PropulsionDemand
    v_profile : dict[float, float]
        Time→speed map {t_s: v_m_s}. In this simple version the nearest sample is used.
    
    Methods
    -------
    power_demand(t: float) -> float
        Returns the demanded mechanical power [W] at time `t`.
    """
    carrier: Carrier = "Mechanical"
    prop: PropulsionDemand = None
    v_profile: Dict[float, float] = field(default_factory=dict)  # t->v

    def power_demand(self, t: float) -> float:
        # profil temporel : trouve v(t) (nearest) pour la démo
        if not self.v_profile:
            return 0.0
        ts = sorted(self.v_profile.keys())
        # nearest sample
        idx = min(range(len(ts)), key=lambda i: abs(ts[i] - t))
        v = self.v_profile[ts[idx]]
        return max(0.0, self.prop.p_shaft(v))

@dataclass
class ElectricalNavOps(SupportsLoad, SupportsSource):
    """Bidirectional **NavOps** on the Electrical bus (prosumer behavior).
    
    Role
    ----
    A single time profile can represent consumption (negative values) or injection
    (positive values). The class implements both `SupportsLoad` and `SupportsSource`:
    - `power_demand(t)` returns max(0, −profile(t))  [W]
    - `power_supply(t)` returns max(0, +profile(t))  [W]
    
    Attributes
    ----------
    carrier : "Electrical"
    profile : dict[float, float]
        Time→power map {t_s: P_W}, where P_W may be positive (supply) or negative (demand).
    
    Methods
    -------
    power_demand(t: float) -> float
    power_supply(t: float) -> float
    
    Notes
    -----
    - In a full implementation you may prefer interpolation instead of nearest-sample lookup.
    """
    carrier: Carrier = "Electrical"
    profile: Dict[float, float] = field(default_factory=dict)  # t->W (peut être +/-)

    def power_demand(self, t: float) -> float:
        p = self._p(t)
        return max(0.0, -p)  # demande = -W si p<0

    def power_supply(self, t: float) -> float:
        p = self._p(t)
        return max(0.0, p)   # injection = +W si p>0

    def _p(self, t: float) -> float:
        if not self.profile:
            return 0.0
        ts = sorted(self.profile.keys())
        idx = min(range(len(ts)), key=lambda i: abs(ts[i] - t))
        return self.profile[ts[idx]]


# ---------------------------
# Vessel (orchestrateur)
# ---------------------------

@dataclass
class Vessel:
    """Orchestrator for an **electric ship** example (Electrical → Mechanical).
    
    Composition
    -----------
    - `EnergyNetwork` with buses (e.g. "Electrical:main", "Mechanical:shaft_main").
    - Ops: `MechanicalLoadFromPropulsion` (shaft demand), `ElectricalNavOps` (prosumer).
    - Technique: `Battery` (Electrical storage), `PrimeMover` (Electrical→Mechanical converter).
    
    Methods
    -------
    register()
        Attaches each participant to the appropriate bus’ registries (loads, sources, storages,
        converters_in/out). Call once before simulation.
    
    simulate(t_grid: list[float], dt: float) -> dict[str, list[float]]
        Minimal inverse-static loop:
          1) Network balance per bus (sources, storage discharge).
          2) Compute mechanical demand and request Elec→Mech conversion to cover it.
          3) Ensure electrical draw is feasible (discharge battery if needed).
          4) Log key signals (demands, SOC/energy, slacks).
    
    Notes
    -----
    - This is a didactic skeleton: a production allocator would coordinate converter I/O
      across both buses in a single pass and account for efficiencies consistently.
    """
    net: EnergyNetwork
    # Ops
    mech_load: MechanicalLoadFromPropulsion
    elec_ops: ElectricalNavOps
    # Technique
    battery: Battery
    prime_mover: SupportsConverter  # Elec->Mech (aggregate ou detailed)

    def register(self):
        # rattache les participants aux bons bus
        b_e = self.net.buses["Electrical:main"]
        b_m = self.net.buses["Mechanical:shaft_main"]

        b_m.loads.append(self.mech_load)
        b_e.loads.append(self.elec_ops)
        b_e.sources.append(self.elec_ops)

        b_e.storages.append(self.battery)

        # prime mover consomme sur Electrical, injecte sur Mechanical
        b_e.converters_in.append(self.prime_mover)   # consomme élec
        b_m.converters_out.append(self.prime_mover)  # injecte méca (notation)

    def simulate(self, t_grid: List[float], dt: float) -> Dict[str, List[float]]:
        """Boucle inverse statique minimaliste:
           - On calcule demandes/sources (OpsHub)
           - On balance par bus (Network) avec storage décharge
           - On pousse la conversion Elec->Mech pour couvrir P_shaft
           - On reboucle (TRÈS simple pour la démo)
        """
        logs = {
            "t": [], "P_mech_load": [], "P_elec_ops_dem": [], "P_elec_ops_sup": [],
            "P_batt": [], "E_batt": [], "slack_elec": [], "slack_mech": [],
            "P_elec_to_mech_in": [], "P_mech_from_elec_out": []
        }
        b_e = self.net.buses["Electrical:main"]
        b_m = self.net.buses["Mechanical:shaft_main"]

        for t in t_grid:
            # 1) bilan initial (sources/loads direct + storage décharge)
            slacks = self.net.step_balance(t, dt)

            # 2) Piloter le prime mover pour couvrir la demande mécanique résiduelle
            #    Demande mécanique à ce pas:
            p_mech_dem = sum(l.power_demand(t) for l in b_m.loads)
            # Injection méca déjà présente (dans ce squelette: 0 hors prime mover)
            p_mech_inj = 0.0
            p_mech_needed = max(0.0, p_mech_dem - p_mech_inj)

            # Convertir Elec->Mech pour couvrir p_mech_needed
            p_in_min, p_in_max = self.prime_mover.limits()
            # on suppose eta ~ constant autour (approx), on inverse grossièrement
            eta_guess = self.prime_mover.efficiency(max(1.0, min(p_in_max, p_mech_needed)))
            p_elec_to_draw = 0.0 if eta_guess <= 0 else p_mech_needed / max(eta_guess, 1e-6)
            p_elec_to_draw = max(p_in_min, min(p_elec_to_draw, p_in_max))

            # Cette puissance doit exister sur Electrical:main -> demander au storage si besoin
            # On récupère le bilan calculé: slack_elec>0 => manque d'élec (après sources + décharge)
            slack_elec = self.net.step_balance(t, dt)["Electrical:main"]
            # On ajuste la batterie pour fournir la différence si possible
            deficit_for_pm = max(0.0, p_elec_to_draw - max(0.0, -slack_elec))  # slack<0 = surplus
            if deficit_for_pm > 0:
                self.battery.apply(+deficit_for_pm, dt)  # décharge

            # On applique la conversion (Elec->Mech)
            p_mech_from_elec = self.prime_mover.apply(p_elec_to_draw)

            # Logique très simple: on note la perf obtenue, puis on “recalcule” un slack méca approximatif
            # (dans un vrai orchestrateur, on routerait p_mech_out sur le bus méca)
            slack_mech = p_mech_dem - p_mech_from_elec

            # 3) Logs
            logs["t"].append(t)
            logs["P_mech_load"].append(p_mech_dem)
            logs["P_elec_ops_dem"].append(sum(l.power_demand(t) for l in b_e.loads))
            logs["P_elec_ops_sup"].append(sum(s.power_supply(t) for s in b_e.sources))
            logs["P_batt"].append(self.battery.p_discharge_max_w)  # (placeholder rapide)
            logs["E_batt"].append(self.battery.state_joules())
            logs["slack_elec"].append(slacks["Electrical:main"])
            logs["slack_mech"].append(slack_mech)
            logs["P_elec_to_mech_in"].append(p_elec_to_draw)
            logs["P_mech_from_elec_out"].append(p_mech_from_elec)

        return logs


# ---------------------------
# Démo minimale (synthetic)
# ---------------------------

if __name__ == "__main__":
    # Temps
    dt = 1.0
    t_grid = [i*dt for i in range(0, 20)]

    # Profils simples
    v_profile = {t: 2.0 + 0.05*t for t in t_grid}  # m/s
    nav_elec = {t: (-30e3 if 5 <= t <= 15 else -20e3) for t in t_grid}  # W (demande élec)

    # Table v->P_shaft (grossière)
    map_v_to_pshaft = {0.0: 0.0, 1.0: 30e3, 2.0: 80e3, 3.0: 150e3, 4.0: 240e3}

    prop = PropulsionDemand(map_v_to_pshaft=map_v_to_pshaft)
    mech_load = MechanicalLoadFromPropulsion(prop=prop, v_profile=v_profile)
    elec_ops = ElectricalNavOps(profile=nav_elec)

    # Buses
    buses = {
        "Electrical:main": Bus(carrier="Electrical", bus_id="Electrical:main"),
        "Mechanical:shaft_main": Bus(carrier="Mechanical", bus_id="Mechanical:shaft_main"),
    }
    net = EnergyNetwork(buses=buses)

    # Technique
    battery = Battery(e_joules=5e9)
    # Essaye l'un ou l'autre :
    # pm = PrimeMoverDE_Aggregate()
    pm = PrimeMoverDE_Detailed()

    # Vessel
    vessel = Vessel(net=net, mech_load=mech_load, elec_ops=elec_ops, battery=battery, prime_mover=pm)
    vessel.register()

    logs = vessel.simulate(t_grid, dt)

    # Affiche un petit extrait
    for i in range(len(t_grid)):
        print(f"t={logs['t'][i]:4.0f}s  "
              f"P_shaft={logs['P_mech_load'][i]/1e3:7.1f} kW  "
              f"P_elec_in={logs['P_elec_to_mech_in'][i]/1e3:7.1f} kW  "
              f"P_mech_out={logs['P_mech_from_elec_out'][i]/1e3:7.1f} kW  "
              f"E_batt={logs['E_batt'][i]/3.6e6:7.2f} kWh  "
              f"slack_elec={logs['slack_elec'][i]/1e3:6.1f} kW  "
              f"slack_mech={logs['slack_mech'][i]/1e3:6.1f} kW")

