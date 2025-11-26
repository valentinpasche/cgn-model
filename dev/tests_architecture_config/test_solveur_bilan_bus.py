# -*- coding: utf-8 -*-
"""
Created on Wed Nov  5 15:47:57 2025

@author: valentin.pasche1
"""

from scipy.optimize import root

def GEN(load, eta):
    "electrique(load) to mecanique(demand)"
    demand = load / eta
    return demand

def ME(load, eta):
    "mecanique(load) to electrique(demand)"
    demand = load / eta
    return demand

def ICE(load, eta):
    "mecanique(load) to chimique(demand)"
    demand = load / eta
    return demand

# Données
eta_ME = 0.8   # -
eta_GEN = 0.9   # -
eta_ICE = 0.5   # -
P_navops_elec = 10.0  # kW
P_shaft_meca  = 1000.0  # kW

P_me_elec = ME(P_shaft_meca, eta_ME)
P_elec_tot = P_me_elec + P_navops_elec
P_gen_meca = GEN(P_elec_tot , eta_GEN)
P_ice_chim = ICE(P_gen_meca, eta_ICE)




# Fonction des résidus : chaque équation doit être = 0 à la solution
def residuals(x):
    """
    x = [P_me_prop, P_gen, P_ice, P_fuel]
    Retourne le vecteur de résidus [r1, r2, r3, r4].
    Le solver va chercher x tel que r_i = 0.
    """
    P_me_prop, P_gen, P_ice, P_fuel = x

    # Équations de bilan et conversions
    r1 = P_me_prop - Pshaft                    # bilan bus mécanique
    r2 = P_me_prop + Pnavops - P_gen           # bilan bus électrique
    r3 = P_gen / eta_GEN - P_ice               # bilan bus électrique
    r4 = P_ice / eta_ICE - P_fuel              # bilan bus chimique

    return [r1, r2, r3, r4]

# Point de départ (approximatif)
x0 = [1000, 1100, 1200, 1300]

sol = root(residuals, x0)

print("\nRésolution:")
print(sol)

if sol.success:
    P_me_prop, P_gen, P_ice, P_fuel = sol.x
    print("\n=== Résultats ===")
    print(f"P_me_prop = {P_me_prop:8.2f} kW")
    print(f"P_gen     = {P_gen:8.2f} kW")
    print(f"P_ice     = {P_ice:8.2f} kW")
    print(f"P_fuel    = {P_fuel:8.2f} kW")
else:
    print("Échec de convergence !")
