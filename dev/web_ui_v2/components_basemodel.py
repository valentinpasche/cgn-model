
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from dash_pydantic_utils import Quantity
from dash_pydantic_utils.quantity.quantity import ISUnits
from dash_pydantic_form import fields


def _register_pci_units() -> None:
    """
    Enregistre les unités PCI custom dans dash_pydantic_utils.Quantity.
    Appelé au chargement du module pour rendre les champs Quantity compatibles.
    """
    # PCI massique: J/kg -> dimensions m^2/s^2
    specific_energy = ISUnits(m=2, s=-2)
    Quantity.register_unit_rates(specific_energy, "J/kg", 1.0, category="SpecificEnergy")
    Quantity.register_unit_rates(specific_energy, "kJ/kg", 1_000.0)
    Quantity.register_unit_rates(specific_energy, "MJ/kg", 1_000_000.0)
    Quantity.register_unit_rates(specific_energy, "kWh/kg", 3_600_000.0)

    # PCI volumique: J/m3 -> dimensions kg/(m*s^2) (même dimension que Pa)
    volumic_energy = ISUnits(kg=1, m=-1, s=-2)
    Quantity.register_unit_rates(volumic_energy, "J/m^3", 1.0)
    Quantity.register_unit_rates(volumic_energy, "kJ/m^3", 1_000.0)
    Quantity.register_unit_rates(volumic_energy, "MJ/m^3", 1_000_000.0)
    Quantity.register_unit_rates(volumic_energy, "kWh/m^3", 3_600_000.0)
    Quantity.register_unit_rates(volumic_energy, "kWh/dm^3", 3_600_000_000.0)


_register_pci_units()


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


default_repr_kwargs = {"decimalScale": 2, "thousandSeparator": "'"}

class EnergyVectorParams(BaseModel):
    pci_basis: Literal["volume", "mass"] = Field(
        title="Type de PCI",
        default="volume",
        repr_kwargs={
            "field_repr": fields.RadioItems(
                options_labels={"volume": "Volumique", "mass": "Massique"}
            )
        },
    )
    pci_mass: Quantity | None = Field(
        title="PCI massique - Valeur et unité",
        default=None,
        repr_type="Quantity",
        repr_kwargs={
            "unit_options": ["kWh/kg", "MJ/kg", "kJ/kg", "J/kg"],
            "visible": ("pci_basis", "==", "mass"),
            **default_repr_kwargs,
        },
    )
    pci_volume: Quantity | None = Field(
        title="PCI volumique - Valeur et unité",
        default=None,
        repr_type="Quantity",
        repr_kwargs={
            "unit_options": {"kWh/dm^3": "kWh/l", "kWh/m^3": "kWh/m³", "MJ/m^3": "MJ/m³", "kJ/m^3": "kJ/m³", "J/m^3": "J/m³"},
            "visible": ("pci_basis", "==", "volume"),
            **default_repr_kwargs,
        },
    )
    density_kg_m3: float | None = Field(title="Densité en kilo par mètre cube", ge=0, default=None, repr_kwargs={"suffix": " kg/m³"})

    @model_validator(mode="after")
    def check_active_pci_field(self):
        # Un seul champ actif requis selon pci_basis.
        if self.pci_basis == "mass":
            if self.pci_mass is None:
                raise ValueError("PCI massique requis quand le type PCI est 'Massique'.")
        elif self.pci_basis == "volume":
            if self.pci_volume is None:
                raise ValueError("PCI volumique requis quand le type PCI est 'Volumique'.")
        return self

class StorageGeneric(BaseModel):
    id: str = Field(title="Nom", description="Nom/identifiant du stockage d'énergie.")
    bus: str | None = Field(title="Sortie puissance", description="Nom du composant en aval.", default="auto-généré", repr_kwargs={"disabled": True})
    vector_energy: str | None = Field(title="Nom du vecteur énergétique", description="Description optionnelle du vecteur énergétique", default=None)
    has_parameters: bool = Field(title="Paramètres spécifiques au vecteur énergétique", description="Définition des paramètres")
    vector_params: EnergyVectorParams | None = Field(
        title="Paramètres du vecteur énergétique",
        description="Déclarer des paramètres spécifiques, pouvoir calorifique inférieur et densité.",
        default=None,
        json_schema_extra={"repr_kwargs": {"visible": ("has_parameters", "==", True)}},
    )

