
from typing import Literal
from pydantic import BaseModel, Field
from dash_pydantic_utils import Quantity
from dash_pydantic_form import fields


class VariableEtaConverter(BaseModel):
    """
    Convertisseur a rendement variable, eta(t).

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
    id: str = Field(title="Nom", description="Nom/identifiant du convertisseur de puissance.")
    from_bus: str | None = Field(title="Entrée puissance", default=None, description="Nom du composant en amont.")
    to_bus: str | None = Field(title="Sortie puissance", description="Nom du composant en aval.", default="auto-généré", repr_kwargs={"disabled": True})
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
    id: str = Field(title="Nom", description="Nom/identifiant du convertisseur de puissance.")
    from_bus: str | None = Field(title="Entrée puissance", default=None, description="Nom du composant en amont.")
    to_bus: str | None = Field(title="Sortie puissance", description="Nom du composant en aval.", default="auto-généré", repr_kwargs={"disabled": True})
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
    id: str = Field(title="Nom", description="Nom/identifiant de l'adaptateur.")
    source: str = Field(title="Profil source", description="Nom du profil de vitesse en entrée.")
    unit_in: Literal["m/s", "km/h", "kn"] = Field(title="Unité entrée", default="m/s")
    unit_out: Literal["W","kW", "MW", "GW"] = Field(title="Unité sortie", default="W")
    coeffs: list[float] = Field(title="Coefficients polynomiaux (ordre croissant)", min_length=1, default_factory=list, description="P(v) = a0 + a1*v + a2*v^2 + ...")


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
    id: str = Field(title="Nom", description="Nom/identifiant de l'adaptateur.")
    force_source: str = Field(title="Profil de force source", description="Nom du profil de force en entrée.")
    speed_source: str = Field(title="Profil de vitesse source", description="Nom du profil de vitesse en entrée.")
    force_unit_in: Literal["N", "kN", "MN"] = Field(title="Unité force", default="N")
    speed_unit_in: Literal["m/s", "km/h", "kn"] = Field(title="Unité vitesse", default="m/s")
    unit_out: Literal["W","kW", "MW", "GW"] = Field(title="Unité puissance", default="W")
    


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
    id: str = Field(title="Nom", description="Nom/identifiant de l'adaptateur.")
    source: str = Field(title="Profil source", description="Nom du profil de vitesse en entrée.")
    unit_in: Literal["m/s", "km/h", "kn"] = Field(title="Unité entrée", default="m/s")
    unit_out: Literal["N", "kN", "MN"] = Field(title="Unité sortie", default="N")
    coeffs: list[float] = Field(title="Coefficients polynomiaux (ordre croissant)", min_length=1, default_factory=list, description="F(v) = a0 + a1*v + a2*v^2 + ...")


default_repr_kwargs = {"decimalScale": 3, "thousandSeparator": "'"}

class MassPCI(BaseModel):
    pci_basis: Literal["mass"]
    pci: Quantity = Field(
        title="PCI massique",
        description="Valeur et unité",
        ge=0,
#        default=None,
        repr_type="Quantity", repr_kwargs={
            "unit_options": ["kWh/kg", "MJ/kg", "kJ/kg", "J/kg"],
            **default_repr_kwargs}
    )

class VolumePCI(BaseModel):
    pci_basis: Literal["volume"]
    pci: Quantity = Field(
        title="PCI volumique",
        description="Valeur et unité",
        ge=0,
#        default=None,
        repr_type="Quantity", repr_kwargs={
            "unit_options": ["kWh/l", "kWh/m3", "MJ/m3", "kJ/m3", "J/m3"],
            **default_repr_kwargs}
    )

class EnergyVectorParams(BaseModel):
    pci_value_unit: VolumePCI | MassPCI = Field(
        title="Pouvoir Calorifique Inférieur",
        description="Exprimé par unité de volume ou de masse.",
#        default=None,
        discriminator="pci_basis",
        repr_kwargs={
            "fields_repr": {"pci_basis": fields.RadioItems(options_labels={"volume": "Volumique", "mass": "Massique"})}
        },
    )
    density_kg_m3: float | None = Field(title="Densité en kilo par mètre cube", ge=0, default=None, repr_kwargs={"suffix": " kg/m3"})

class StorageGeneric(BaseModel):
    id: str = Field(title="Nom", description="Nom/identifiant du stockage d'énergie.")
    bus: str | None = Field(title="Sortie puissance", description="Nom du composant en aval.", default="auto-généré", repr_kwargs={"disabled": True})
    vector_energy: str | None = Field(title="Nom du vecteur énergétique", description="Description optionnelle du vecteur énergétique", default=None)
    has_parameters: bool = Field(title="Paramètres spécifiques au vecteur énergétique", description="Définition des paramètres")
    vector_params: EnergyVectorParams | None = Field(
        title="Paramètres du vecteur énergétique",
        default=None,
        json_schema_extra={"repr_kwargs": {"visible": ("has_parameters", "==", True)}},
    )

