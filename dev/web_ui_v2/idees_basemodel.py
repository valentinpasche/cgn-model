
from pydantic import BaseModel, Field

class VariableEtaConverter(BaseModel):
    """
    Convertisseur a rendement variable dans le temps.

    Parameters
    ----------
    id : str
        Identifiant du convertisseur.
    from_bus : str
        Bus en entree.
    to_bus : str
        Bus en sortie.
    eta_source : str | None
        ID d'un profil eta(t).
    """
    id: str = Field(title="Nom")
    from_bus: str | None = Field(title="Entrée puissance", default=None)
    to_bus: str | None = Field(title="Sortie puissance", default=None)
    eta_source: str = Field(title="Profil de rendement, (0 < eta <= 1)")


class ConstantEtaConverter(BaseModel):
    """
    Convertisseur a rendement constant.

    Parameters
    ----------
    id : str
        Identifiant du convertisseur.
    from_bus : str
        Bus en entree.
    to_bus : str
        Bus en sortie.
    eta : float
        Rendement constant (0 < eta <= 1).
    """
    id: str = Field(title="Nom")
    from_bus: str | None = Field(title="Entrée puissance", default=None)
    to_bus: str | None = Field(title="Sortie puissance", default=None)
    eta: float = Field(title="Rendement, (0 < eta <= 1)", gt=0, le=1, allow_inf_nan=False)



class SpeedToPowerPolyAdapter(BaseModel):
    """
    Adaptateur vitesse -> puissance via polynome.

    Parameters
    ----------
    coeffs : tuple[float, ...]
        Coefficients (a0, a1, a2, ...).
    unit_in : str
        Unite attendue en entree (ex. "m/s").
    unit_out : str
        Unite de sortie (ex. "W").

    Notes
    -----
    - P(v) = a0 + a1*v + a2*v^2 + ...
    - Conversion d'unites automatique vers unit_in.
    """
    id: str = Field(title="Nom")
    source: str = Field(title="Profil source")
    unit_in: str = Field(title="Unité entrée", default="m/s")
    unit_out: str = Field(title="Unité sortie", default="W")
    coeffs: list[float] = Field(title="Coefficients polynomiaux (ordre croissant)", min_length=1)


class ForceAndSpeedToPowerAdapter(BaseModel):
    """
    Adaptateur multi-entrees: puissance = force * vitesse.

    Parameters
    ----------
    force_source : str
        ID de la source force.
    speed_source : str
        ID de la source vitesse.
    force_unit_in : str
        Unite attendue pour la force (ex. "N").
    speed_unit_in : str
        Unite attendue pour la vitesse (ex. "m/s").
    unit_out : str
        Unite de sortie (ex. "W").

    Notes
    -----
    - P = F * v (en SI, W).
    """
    id: str = Field(title="Nom")
    force_source: str = Field(title="Profil de force source")
    speed_source: str = Field(title="Profil de vitesse source")
    force_unit_in: str = Field(title="Unité puissance", default="N")
    speed_unit_in: str = Field(title="Unité vitesse", default="m/s")
    unit_out: str = Field(title="Unité sortie", default="W")
    


class SpeedToForcePoly(BaseModel):
    """
    Adaptateur vitesse -> force via polynome.

    Parameters
    ----------
    coeffs : tuple[float, ...]
        Coefficients (a0, a1, a2, ...).
    unit_in : str
        Unite attendue en entree (ex. "m/s").
    unit_out : str
        Unite de sortie (ex. "N").

    Notes
    -----
    - F(v) = a0 + a1*v + a2*v^2 + ...
    - Conversion d'unites automatique vers unit_in.
    """
    id: str = Field(title="Nom")
    source: str = Field(title="Profil source")
    unit_in: str = Field(title="Unité entrée", default="m/s")
    unit_out: str = Field(title="Unité sortie", default="N")
    coeffs: list[float] = Field(title="Coefficients polynomiaux (ordre croissant)", min_length=1)
    
