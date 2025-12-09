# Test pour valider les croisiere
# Y compris pour y intéger la "reprise" du delay sur l'étapes suivante

from cgn_model.navigation import Croisiere, SpeedProfileParams
import warnings


params = SpeedProfileParams(
)

croisieres = Croisiere.from_cgn_croisiere_csv("all")

# ---- Test continuité + __repr__
for c in croisieres:
    assert c.check_continuite()
    print("======"*10)
    Croisiere.view_croisiere(c)


# ---- ALL - Calcul profile vitesse

c_profiles = []
for c in croisieres:
    print("======" * 10)
    print(c.nom)
    print()

    # On capture les warnings de CETTE croisière uniquement
    with warnings.catch_warnings(record=True) as wlist:
        warnings.simplefilter("always")  # forcer l’enregistrement de tous les warnings
        p, _ = c.speed_profile(params)

    c_profiles.append(p)

    # Affichage des warnings pour cette croisière
    if wlist:
        print("  -- Warnings pour cette croisière --")
        for w in wlist:
            # w.message est déjà un objet Warning → str(w.message)
            print("   ", w.message)
    else:
        print("  (aucun warning)")

    print()  # ligne vide pour la lisibilité


    
        