# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Protocol, Tuple, Literal
import math

Carrier = Literal["Electrical", "Mechanical", "Thermal", "Chemical"]

# ---------------------------
# Protocols (interfaces)
# ---------------------------
class SupportsLoad(Protocol):
    carrier: Carrier
    def power_demand(self, t: float) -> float: ...

class SupportsSource(Protocol):
    carrier: Carrier
    def power_supply(self, t: float) -> float: ...

class SupportsConverter(Protocol):
    from_carrier: Carrier
    to_carrier: Carrier
    def limits(self) -> Tuple[float, float]: ...
    def efficiency(self, p_in_w: float) -> float: ...
    def p_out(self, p_in_w: float) -> float: ...

class SupportsStorage(Protocol):
    carrier: Carrier
    def limits(self) -> Tuple[float, float]: ...
    def state_joules(self) -> float: ...
    def apply(self, p_net_w: float, dt: float) -> float: ...


# ---------------------------
# Bus + Network (une passe)
# ---------------------------
@dataclass
class Bus:
    carrier: Carrier
    bus_id: str
    loads: List[SupportsLoad] = field(default_factory=list)
    sources: List[SupportsSource] = field(default_factory=list)
    converters_in: List[SupportsConverter] = field(default_factory=list)    # consomme ici
    converters_out: List[SupportsConverter] = field(default_factory=list)   # injecte ici
    storages: List[SupportsStorage] = field(default_factory=list)

    # accumulés par pas
    demand_W: float = 0.0
    supply_W: float = 0.0
    storage_W: float = 0.0  # + décharge, - charge

    def reset(self):
        self.demand_W = 0.0
        self.supply_W = 0.0
        self.storage_W = 0.0

@dataclass
class EnergyNetwork:
    buses: Dict[str, Bus]

    def single_pass_balance(self, t: float, dt: float):
        """Bilan simple: on intègre loads/sources tels quels; pas de dispatch automatique.
        Ici, c'est l'orchestrateur qui décide des puissances des convertisseurs et appelle les storages.
        """
        for bus in self.buses.values():
            bus.reset()
            bus.demand_W += sum(max(0.0, l.power_demand(t)) for l in bus.loads)
            bus.supply_W += sum(max(0.0, s.power_supply(t)) for s in bus.sources)

    def slack(self, bus_id: str) -> float:
        """>0 : manque (demande non couverte), <0 : surplus."""
        b = self.buses[bus_id]
        return b.demand_W - (b.supply_W + b.storage_W)


# ---------------------------
# OpsHub (v -> P_shaft ; NavOps élec bidirectionnel)
# ---------------------------
@dataclass
class PropulsionDemand:
    map_v_to_pshaft: Dict[float, float]
    def p_shaft(self, v: float) -> float:
        xs = sorted(self.map_v_to_pshaft)
        if v <= xs[0]: return self.map_v_to_pshaft[xs[0]]
        if v >= xs[-1]: return self.map_v_to_pshaft[xs[-1]]
        for i in range(len(xs)-1):
            x0, x1 = xs[i], xs[i+1]
            if x0 <= v <= x1:
                y0, y1 = self.map_v_to_pshaft[x0], self.map_v_to_pshaft[x1]
                a = (v - x0) / (x1 - x0)
                return y0 + a * (y1 - y0)
        return 0.0

@dataclass
class MechanicalLoadFromSpeed(SupportsLoad):
    carrier: Carrier = "Mechanical"
    prop: PropulsionDemand = None
    v_profile: Dict[float, float] = field(default_factory=dict)
    def power_demand(self, t: float) -> float:
        if not self.v_profile: return 0.0
        ts = sorted(self.v_profile)
        ti = min(ts, key=lambda x: abs(x - t))
        return max(0.0, self.prop.p_shaft(self.v_profile[ti]))

@dataclass
class ElectricalNavOps(SupportsLoad, SupportsSource):
    carrier: Carrier = "Electrical"
    profile_W: Dict[float, float] = field(default_factory=dict)  # + supply, - load
    def _p(self, t: float) -> float:
        if not self.profile_W: return 0.0
        ts = sorted(self.profile_W)
        ti = min(ts, key=lambda x: abs(x - t))
        return self.profile_W[ti]
    def power_demand(self, t: float) -> float:  # demande = -min(0,p)
        p = self._p(t)
        return max(0.0, -p)
    def power_supply(self, t: float) -> float:  # injection = max(0,p)
        p = self._p(t)
        return max(0.0, p)


# ---------------------------
# ConverterHub (Elec->Mech ; Mech->Elec si besoin)
# ---------------------------
@dataclass
class PrimeMoverDE(SupportsConverter):
    """Elec -> Mech, η variable douce en fonction de la charge relative."""
    from_carrier: Carrier = "Electrical"
    to_carrier: Carrier = "Mechanical"
    p_rated_w: float = 800e3
    eta_nominal: float = 0.92
    p_in_min_w: float = 0.0
    p_in_max_w: float = 800e3
    def limits(self) -> Tuple[float, float]: return (self.p_in_min_w, self.p_in_max_w)
    def efficiency(self, p_in_w: float) -> float:
        x = max(0.0, min(1.0, p_in_w / max(1.0, self.p_rated_w)))
        eta = self.eta_nominal * (0.9 + 0.2 * x)
        return max(0.5, min(0.98, eta))
    def p_out(self, p_in_w: float) -> float:
        p = max(self.p_in_min_w, min(p_in_w, self.p_in_max_w))
        return p * self.efficiency(p)

# (facultatif) Generator Mech->Elec, non utilisé ici

# ---------------------------
# StorageHub (FuelTank), Genset (Chem->Elec via SFC)
# ---------------------------
@dataclass
class FuelTank(SupportsStorage):
    carrier: Carrier = "Chemical"
    pci_j_per_kg: float = 42.6e6
    density_kg_per_m3: float = 840.0
    energy_j: float = 1.0e10
    p_discharge_max_w: float = 2.0e6
    p_charge_max_w: float = 0.0  # pas de recharge dans ce MVP
    consumed_kg_total: float = 0.0
    def limits(self) -> Tuple[float, float]:
        return (self.p_discharge_max_w, self.p_charge_max_w)
    def state_joules(self) -> float: return self.energy_j
    def apply(self, p_net_w: float, dt: float) -> float:
        # +W => décharge chimique (retire de l'énergie)
        if p_net_w <= 0: return 0.0
        p = min(self.p_discharge_max_w, p_net_w)
        e = p * dt
        e = min(e, self.energy_j)
        self.energy_j -= e
        # tenir un compteur massique à partir de l'énergie soutirée
        self.consumed_kg_total += e / self.pci_j_per_kg
        return + (e / dt)

@dataclass
class GensetGroup:
    """Chem -> Elec via SFC(kW)->g/kWh. Ici on ne le “branche” pas comme converter générique,
       on le traite comme un producteur électrique alimenté par FuelTank.
    """
    sfc_kW_g_per_kWh: Dict[float, float]  # table
    p_out_max_w: float = 1.0e6
    def sfc(self, p_out_w: float) -> float:
        """g/kWh via interpolation (clamp)."""
        xs = sorted(self.sfc_kW_g_per_kWh)
        ys = [self.sfc_kW_g_per_kWh[x] for x in xs]
        p_kw = max(0.0, p_out_w / 1e3)
        if p_kw <= xs[0]: return ys[0]
        if p_kw >= xs[-1]: return ys[-1]
        for i in range(len(xs)-1):
            if xs[i] <= p_kw <= xs[i+1]:
                a = (p_kw - xs[i]) / (xs[i+1]-xs[i])
                return ys[i] + a*(ys[i+1]-ys[i])
        return ys[-1]
    def fuel_kg_per_s_for(self, p_out_w: float) -> float:
        sfc_g_per_kWh = self.sfc(p_out_w)
        p_kw = max(0.0, p_out_w/1e3)
        # kg/s = (kW * g/kWh / 1000) / 3600
        return (p_kw * (sfc_g_per_kWh/1000.0)) / 3600.0


# ---------------------------
# Vessel (orchestrateur propre, une passe)
# ---------------------------
@dataclass
class Vessel:
    net: EnergyNetwork
    # Ops
    mech_load: MechanicalLoadFromSpeed
    elec_navops: ElectricalNavOps
    # Technique
    prime_mover: PrimeMoverDE
    fuel_tank: FuelTank
    genset: GensetGroup

    def register(self):
        b_e = self.net.buses["Electrical:main"]
        b_m = self.net.buses["Mechanical:shaft_main"]
        b_c = self.net.buses["Chemical:fuel_main"]

        b_m.loads.append(self.mech_load)
        b_e.loads.append(self.elec_navops)
        b_e.sources.append(self.elec_navops)

        # On ne connecte pas Genset via converters_in/out ici : on le “pilote” dans la passe.

        # FuelTank attaché au bus chimique (pour le suivi d’énergie)
        b_c.storages.append(self.fuel_tank)

        # Prime mover comme converter Elec->Mech (piloté via root-finding)
        b_e.converters_in.append(self.prime_mover)
        b_m.converters_out.append(self.prime_mover)

    # --- utilitaires ---
    def _bisect_for_pm_input(self, p_target_out_w: float, tol: float = 1e-2) -> float:
        """Trouve p_in tel que pm.p_out(p_in) ≈ p_target_out (borné)."""
        lo, hi = self.prime_mover.limits()
        # si la cible dépasse le max possible:
        if self.prime_mover.p_out(hi) <= p_target_out_w:
            return hi
        # bisection
        for _ in range(40):
            mid = 0.5*(lo+hi)
            if self.prime_mover.p_out(mid) >= p_target_out_w:
                hi = mid
            else:
                lo = mid
            if (hi-lo) <= tol:
                break
        return 0.5*(lo+hi)

    def simulate(self, t_grid: List[float], dt: float) -> Dict[str, List[float]]:
        logs = {k: [] for k in [
            "t","P_shaft","P_pm_in","P_pm_out","slack_mech",
            "P_elec_nav_dem","P_elec_nav_sup","P_genset_out","slack_elec",
            "Fuel_kg_total","Fuel_E_J"
        ]}
        b_e = self.net.buses["Electrical:main"]
        b_m = self.net.buses["Mechanical:shaft_main"]
        b_c = self.net.buses["Chemical:fuel_main"]

        for t in t_grid:
            # 1) reset + loads/sources OpsHub
            self.net.single_pass_balance(t, dt)
            # 2) calcule la demande mécanique à l’arbre (après single_pass, b_m.demand_W est OK)
            P_shaft = b_m.demand_W

            # 3) résout l’entrée élec du prime mover pour couvrir P_shaft
            P_pm_in = 0.0
            P_pm_out = 0.0
            if P_shaft > 0:
                P_pm_in = self._bisect_for_pm_input(P_shaft)
                P_pm_out = self.prime_mover.p_out(P_pm_in)

            # 4) poste les contributions convertisseur sur les bus (pas de double balance)
            b_e.demand_W += P_pm_in            # Elec consomme P_pm_in
            b_m.supply_W += P_pm_out           # Méca reçoit P_pm_out

            # 5) slack mécanique (manque résiduel si PM saturé)
            slack_mech = max(0.0, b_m.demand_W - b_m.supply_W)

            # 6) couvrir la demande électrique nette avec le groupe + fuel tank
            P_elec_net_needed = max(0.0, b_e.demand_W - b_e.supply_W)
            # bornes du groupe
            P_genset_out = min(P_elec_net_needed, self.genset.p_out_max_w)
            # convertir en fuel -> demander énergie chimique au FuelTank
            fuel_kg_s = self.genset.fuel_kg_per_s_for(P_genset_out)
            fuel_J_s  = fuel_kg_s * self.fuel_tank.pci_j_per_kg   # puissance chimique demandée
            # soutirer du tank (limité par son p_discharge_max_w et stock)
            P_chem_from_tank = self.fuel_tank.apply(+fuel_J_s, dt)

            # si le tank ne peut pas fournir assez (stock/puissance), réduis P_genset_out au prorata
            if fuel_J_s > 0:
                ratio = max(0.0, min(1.0, P_chem_from_tank / fuel_J_s))
            else:
                ratio = 1.0
            P_genset_out *= ratio

            # crédite la prod élec (après fuel effectif)
            b_e.supply_W += P_genset_out

            # 7) slack élec final (positif => manque)
            slack_elec = max(0.0, b_e.demand_W - b_e.supply_W)

            # 8) logs
            logs["t"].append(t)
            logs["P_shaft"].append(P_shaft)
            logs["P_pm_in"].append(P_pm_in)
            logs["P_pm_out"].append(P_pm_out)
            logs["slack_mech"].append(slack_mech)
            logs["P_elec_nav_dem"].append(sum(l.power_demand(t) for l in b_e.loads))
            logs["P_elec_nav_sup"].append(sum(s.power_supply(t) for s in b_e.sources))
            logs["P_genset_out"].append(P_genset_out)
            logs["slack_elec"].append(slack_elec)
            logs["Fuel_kg_total"].append(self.fuel_tank.consumed_kg_total)
            logs["Fuel_E_J"].append(self.fuel_tank.state_joules())

        return logs


# ---------------------------
# Démo minimale (mêmes équations, mais modulaires)
# ---------------------------
if __name__ == "__main__":
    # Temps
    dt = 1.0
    t_grid = [i*dt for i in range(0, 60)]

    # Profils
    v_profile = {t: 2.0 + 0.03*t for t in t_grid}  # m/s
    nav_elec  = {t: (-30e3 if 10 <= t <= 40 else -20e3) for t in t_grid}  # W (prosumer négatif = load)

    # Tables
    map_v_pshaft = {0.0:0.0, 1.0:30e3, 2.0:80e3, 3.0:150e3, 4.0:240e3, 5.0:360e3}
    sfc_map = {0.0: 280.0, 100.0: 240.0, 400.0: 215.0, 800.0: 205.0}  # kW -> g/kWh

    # Ops
    prop = PropulsionDemand(map_v_to_pshaft=map_v_pshaft)
    mech_load = MechanicalLoadFromSpeed(prop=prop, v_profile=v_profile)
    elec_ops  = ElectricalNavOps(profile_W=nav_elec)

    # Buses
    buses = {
        "Electrical:main": Bus(carrier="Electrical", bus_id="Electrical:main"),
        "Mechanical:shaft_main": Bus(carrier="Mechanical", bus_id="Mechanical:shaft_main"),
        "Chemical:fuel_main": Bus(carrier="Chemical", bus_id="Chemical:fuel_main"),
    }
    net = EnergyNetwork(buses=buses)

    # Technique
    pm = PrimeMoverDE(p_rated_w=800e3, eta_nominal=0.92, p_in_max_w=800e3)
    tank = FuelTank(energy_j=1.4e10)  # ~ 3.9 MWh PCI
    genset = GensetGroup(sfc_kW_g_per_kWh=sfc_map, p_out_max_w=800e3)

    # Vessel
    vessel = Vessel(net=net, mech_load=mech_load, elec_navops=elec_ops,
                    prime_mover=pm, fuel_tank=tank, genset=genset)
    vessel.register()

    logs = vessel.simulate(t_grid, dt)

    # Affiche un petit extrait
    for i in range(0, len(t_grid), 5):
        print(f"t={logs['t'][i]:4.0f}s  "
              f"P_shaft={logs['P_shaft'][i]/1e3:7.1f} kW  "
              f"P_pm_in={logs['P_pm_in'][i]/1e3:7.1f} kW  "
              f"P_pm_out={logs['P_pm_out'][i]/1e3:7.1f} kW  "
              f"P_gen={logs['P_genset_out'][i]/1e3:7.1f} kW  "
              f"slack_elec={logs['slack_elec'][i]/1e3:6.1f} kW  "
              f"slack_mech={logs['slack_mech'][i]/1e3:6.1f} kW  "
              f"Fuel_tot={logs['Fuel_kg_total'][i]:6.2f} kg")
