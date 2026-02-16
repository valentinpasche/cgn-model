# -*- coding: utf-8 -*-
"""
Test pour valider les coefficients des adaptateurs.

L'arrondi à 3 chiffres après la virgule change la force de 0.78% W le résulat final...
"""

import numpy as np
from numpy.polynomial import polynomial

v_kmh = np.arange(0, 25.45, 0.05)

coefs_base_full = [0.002038,	0.040937, 0.528592, -0.208722] # Input brut
coefs_base = [0.002, 0.041, 0.529, -0.209] # Arrondi à 3 chiffres
coefs_base = list(reversed(coefs_base))

force_base_newton = polynomial.polyval(v_kmh, coefs_base)*1000

v_ms = v_kmh / 3.6

coefs_kmh_newton = polynomial.polyfit(v_kmh, force_base_newton, 3)
coefs_ms_newton = polynomial.polyfit(v_ms, force_base_newton, 3)

force_ms_newton = polynomial.polyval(v_ms, coefs_ms_newton)

p_kmh = force_base_newton * v_ms
p_ms = force_ms_newton * v_ms



coefs_eta_kmh = [-1.21965e-5, 0.000336977, 0.009896235, 0.111383068]
coefs_eta_kmh = list(reversed(coefs_eta_kmh))

eta_kmh = polynomial.polyval(v_kmh, coefs_eta_kmh)
coefs_eta_ms = polynomial.polyfit(v_ms, eta_kmh, 3)

eta_ms = polynomial.polyval(v_ms, coefs_eta_ms)


