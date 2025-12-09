# -*- coding: utf-8 -*-
"""
Created on Tue Dec  9 12:51:26 2025

@author: valentin.pasche1
"""

import numpy as np
import matplotlib.pyplot as plt
from numpy.polynomial import polynomial

v_kmh = np.arange(0, 25.45, 0.05)

coefs_base = [0.002, 0.041, 0.529, -0.209]
coefs_base = list(reversed(coefs_base))

force_base_newton = polynomial.polyval(v_kmh, coefs_base)*1000

v_ms = v_kmh / 3.6

coefs_kmh_newton = polynomial.polyfit(v_kmh, force_base_newton, 3)
coefs_ms_newton = polynomial.polyfit(v_ms, force_base_newton, 3)

force_ms_newton = polynomial.polyval(v_ms, coefs_ms_newton)

p_ms = force_ms_newton * v_ms

p_kmh = force_base_newton * v_ms

