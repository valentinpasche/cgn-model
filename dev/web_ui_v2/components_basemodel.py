
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


def _register_speed_units() -> None:
    """
    Enregistre les unités de vitesse custom dans dash_pydantic_utils.Quantity.
    Appelé au chargement du module pour rendre les champs Quantity compatibles.
    """
    # Vitesse en noeud: kn -> dimensions m/s
    specific_speed = ISUnits(m=1, s=-1)
    Quantity.register_unit_rates(specific_speed, "kn", (1852/3600), category="SpecificSpeed")

_register_speed_units()


class VariableEtaConverter(BaseModel):
    """
    Convertisseur a rendement variable, eta(t)

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
    to_bus: str | None = Field(
        title="Sortie puissance",
        description="Nom du composant en aval.",
        default="auto-généré",
        json_schema_extra={"repr_kwargs": {"disabled": True}},
    )
    eta_source: str = Field(title="Profil de rendement, (0 < eta <= 1)", description="Nom/identifiant du profil de rendement source.")


class ConstantEtaConverter(BaseModel):
    """
    Convertisseur a rendement constant

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
    to_bus: str | None = Field(
        title="Sortie puissance",
        description="Nom du composant en aval.",
        default="auto-généré",
        json_schema_extra={"repr_kwargs": {"disabled": True}},
    )
    eta: float = Field(title="Rendement, (0 < eta <= 1)", gt=0, le=1, allow_inf_nan=False, description="Valeur numérique entre 0 et 1.")


class PowerToPowerPolyAdapter(BaseModel):
    """
    Adaptateur puissance -> puissance via polynome

    Parameters
    ----------
    coeffs : tuple[float, ...]
        Coefficients (a0, a1, a2, ...).
    unit_in : str
        Unite attendue en entree (ex. "kW").
    unit_out : str
        Unite de sortie (ex. "W").

    Notes
    -----
    - P(p) = a0 + a1*p + a2*p^2 + ...
    - Conversion d'unites automatique vers unit_in.
    """
    id: str = Field(title="Nom", description="Nom/identifiant de l'adaptateur.")
    source: str = Field(title="Profil source", description="Nom du profil de puissance en entrée.")
    target: str = Field(title="Convertisseur cible", description="Nom/identifiant du convertisseur cible.")
    unit_in: Literal["W","kW", "MW", "GW"] = Field(title="Unité de puissance, en entrée", default="W")
    unit_out: Literal["W","kW", "MW", "GW"] = Field(title="Unité de puissance, en sortie", default="W")
    coeffs: list[float] = Field(
        title="Coefficients polynomiaux (ordre croissant)",
        min_length=2,
        default_factory=lambda: [0.0, 1.0],
        validate_default=True,
        description="P(p) = a0 + a1*p + a2*p^2 + ...",
    )


class SpeedToPowerPolyAdapter(BaseModel):
    """
    Adaptateur vitesse -> puissance via polynome

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
    target: str = Field(title="Convertisseur cible", description="Nom/identifiant du convertisseur cible.")
    unit_in: Literal["m/s", "km/h", "kn"] = Field(title="Unité de vitesse, en entrée", default="m/s")
    unit_out: Literal["W","kW", "MW", "GW"] = Field(title="Unité de puissance, en sortie", default="W")
    coeffs: list[float] = Field(
        title="Coefficients polynomiaux (ordre croissant)",
        min_length=1,
        default_factory=list,
        validate_default=True,
        description="P(v) = a0 + a1*v + a2*v^2 + ...",
    )


class ForceAndSpeedToPowerAdapter(BaseModel):
    """
    Adaptateur multi-entrees: puissance = force * vitesse

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
    target: str = Field(title="Convertisseur cible", description="Nom/identifiant du convertisseur cible.")
    force_unit_in: Literal["N", "kN", "MN"] = Field(title="Unité de force, en entrée", default="N")
    speed_unit_in: Literal["m/s", "km/h", "kn"] = Field(title="Unité de vitesse, en entrée", default="m/s")
    unit_out: Literal["W","kW", "MW", "GW"] = Field(title="Unité de puissance, en sortie", default="W")
    

class SpeedToForcePoly(BaseModel):
    """
    Adaptateur vitesse -> force via polynome

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
    target: str = Field(title="Convertisseur cible", description="Nom/identifiant du convertisseur cible.")
    unit_in: Literal["m/s", "km/h", "kn"] = Field(title="Unité de vitesse, en entrée", default="m/s")
    unit_out: Literal["N", "kN", "MN"] = Field(title="Unité de force, en sortie", default="N")
    coeffs: list[float] = Field(
        title="Coefficients polynomiaux (ordre croissant)",
        min_length=1,
        default_factory=list,
        validate_default=True,
        description="F(v) = a0 + a1*v + a2*v^2 + ...",
    )


default_repr_kwargs = {"decimalScale": 2, "thousandSeparator": "'"}

class EnergyVectorParams(BaseModel):
    pci_basis: Literal["volume", "mass"] = Field(
        title="Type de PCI",
        default="volume",
        json_schema_extra={
            "repr_type": "RadioItems",
            "repr_kwargs": {
                "options_labels": {"volume": "Volumique", "mass": "Massique"}
            },
        },
    )
    density_kg_m3: float = Field(
        title="Densité en kilo par mètre cube (obligatoire)",
        gt=0.01,
        default=850.0,
        json_schema_extra={"repr_kwargs": {"suffix": " kg/m³", **default_repr_kwargs}},
    )
    pci_mass: Quantity | None = Field(
        title="PCI massique - Valeur et unité",
        default_factory=lambda: Quantity(value=42.6, unit="MJ/kg"),
        json_schema_extra={
            "repr_type": "Quantity",
            "repr_kwargs": {
                "unit_options": ["kWh/kg", "MJ/kg", "kJ/kg", "J/kg"],
                "min": 0.01,
                "visible": ("pci_basis", "==", "mass"),
                **default_repr_kwargs,
            },
        },
    )
    pci_volume: Quantity | None = Field(
        title="PCI volumique - Valeur et unité",
        default_factory=lambda: Quantity(value=10.06, unit="kWh/dm^3"),
        json_schema_extra={
            "repr_type": "Quantity",
            "repr_kwargs": {
                "unit_options": {"kWh/dm^3": "kWh/l", "kWh/m^3": "kWh/m³", "MJ/m^3": "MJ/m³", "kJ/m^3": "kJ/m³", "J/m^3": "J/m³"},
                "min": 0.01,
                "visible": ("pci_basis", "==", "volume"),
                **default_repr_kwargs,
            },
        },
    )

    @model_validator(mode="after")
    def check_active_pci_field(self):
        # Un seul champ actif requis selon pci_basis.
        if self.pci_basis == "mass":
            if self.pci_mass is None:
                raise ValueError("PCI massique requis quand le type PCI est 'Massique'.")
            if float(self.pci_mass.value) <= 0:
                raise ValueError("Le PCI massique doit etre strictement positif.")
        elif self.pci_basis == "volume":
            if self.pci_volume is None:
                raise ValueError("PCI volumique requis quand le type PCI est 'Volumique'.")
            if float(self.pci_volume.value) <= 0:
                raise ValueError("Le PCI volumique doit etre strictement positif.")
        return self

class InitialStorageLevelFuel(BaseModel):
    value: Quantity = Field(
        title="Niveau initial - Combustible",
        default_factory=lambda: Quantity(value=0.0, unit="dm^3"),
        json_schema_extra={
            "repr_type": "Quantity",
            "repr_kwargs": {
                "unit_options": {"kg": "kg", "Mg": "tonne", "dm^3": "litre", "m^3": "m³", "kWh": "kWh", "Wh": "Wh", "MWh": "MWh", "J": "J", "kJ": "kJ", "MJ": "MJ"},
                "min": 0.0,
                **default_repr_kwargs,
            },
        },
    )

    @model_validator(mode="after")
    def check_non_negative_level(self):
        if float(self.value.value) < 0:
            raise ValueError("Le niveau initial combustible doit etre >= 0.")
        return self

class InitialStorageLevelElectrical(BaseModel):
    value: Quantity = Field(
        title="Niveau initial - Electrique",
        default_factory=lambda: Quantity(value=0.0, unit="kWh"),
        json_schema_extra={
            "repr_type": "Quantity",
            "repr_kwargs": {
                "unit_options": ["kWh", "Wh", "MWh", "J", "kJ", "MJ"],
                "min": 0.0,
                **default_repr_kwargs,
            },
        },
    )

    @model_validator(mode="after")
    def check_non_negative_level(self):
        if float(self.value.value) < 0:
            raise ValueError("Le niveau initial electrique doit etre >= 0.")
        return self

class StorageFuel(BaseModel):
    """
    Stockage - Combustible (avec PCI)
    """
    id: str = Field(title="Nom", description="Nom/identifiant du stockage d'énergie.")
    bus: str | None = Field(
        title="Sortie puissance",
        description="Nom du composant en aval.",
        default="auto-généré",
        json_schema_extra={"repr_kwargs": {"disabled": True}},
    )
    vector_energy: str | None = Field(title="Nom du vecteur énergétique", description="Description optionnelle du vecteur énergétique.", default=None)
    vector_params: EnergyVectorParams = Field(
        title="Paramètres spécifiques - Combustibe",
        description="Déclarer des paramètres spécifiques, pouvoir calorifique inférieur et densité.",
        default_factory=EnergyVectorParams,
    )
    initial_level_fuel: InitialStorageLevelFuel = Field(
        title="Etat initial du stockage - Combustible",
        description="Etat initial (énergie/masse/volume). Mettre 0 pour démarrer vide.",
        default_factory=InitialStorageLevelFuel,
    )

class StorageGeneric(BaseModel):
    """
    Stockage - Générique / Electrique (sans PCI)
    """
    id: str = Field(title="Nom", description="Nom/identifiant du stockage d'énergie.")
    bus: str | None = Field(
        title="Sortie puissance",
        description="Nom du composant en aval.",
        default="auto-généré",
        json_schema_extra={"repr_kwargs": {"disabled": True}},
    )
    vector_energy: str | None = Field(title="Nom du vecteur énergétique", description="Description optionnelle du vecteur énergétique.", default=None)
    initial_level_electrical: InitialStorageLevelElectrical = Field(
        title="Etat initial du stockage - Electrique (énergie)",
        description="Etat initial (énergie). Mettre 0 pour démarrer vide.",
        default_factory=InitialStorageLevelElectrical,
    )


class SchemaComponentRef(BaseModel):
    """
    Ligne composant dans un schema UI.
    """

    name: str = Field(title="Nom du composant", description="Nom/ID du composant en base.")
    status: str = Field(
        title="Statut",
        description="Statut d'existance en base.",
        default="N/A",
        json_schema_extra={"repr_kwargs": {"disabled": True}},
    )
    model: str = Field(
        title="Modele",
        description="Modele detecte (type.kind).",
        default="N/A",
        json_schema_extra={"repr_kwargs": {"disabled": True}},
    )


class SchemaDraft(BaseModel):
    """
    Schema (liste de references composants).
    """

    name: str = Field(title="Nom du schema", description="Nom unique du schema.")
    components: list[SchemaComponentRef] = Field(
        title="Composants du schema",
        description="Table des composants. Utiliser 'Add row' pour ajouter des lignes.",
        min_length=1,
        default_factory=list,
    )


class ConstantProfile(BaseModel):
    """
    Profil constant
    """
    id: str = Field(title="Nom", description="Nom/identifiant du profil d'entrée.")
    unit: str = Field(title="Unité du profil", description="Unité de la valeur constante.")
    value: float = Field(title="Valeur", default_factory=float)

class SeriesProfile(BaseModel):
    """
    Profil serie explicite
    """
    id: str = Field(title="Nom", description="Nom/identifiant du profil d'entrée.")
    unit: str = Field(title="Unité du profil", description="Unité de la série de valeurs.")
    data: list[float] = Field(title="Liste de valeur", min_length=1, default_factory=list, description="e.g., 45.90 | 48.0 | 50.2 | 41.02| 32.0")

class FileProfile(BaseModel):
    """
    Profil chargé depuis un fichier CSV
    """
    id: str = Field(title="Nom", description="Nom/identifiant du profil d'entrée.")
    file: str = Field(
        title=r"Nom du CSV (e.g. 'C:\\Users\\...\\data.csv')",
        description="Chemin d'acces complet (absolu) du fichier CSV d'entree.",
    )
    column: str | None = Field(title="Entête de la colonne contenant les valeurs", description="Si le champ est laisé vide, la première colonne est utilisée.", default=None)
    unit: str = Field(title="Unité du profil", description="Unité des valeurs de la colonne du fichier CSV.")
    sep: Literal["auto", ",", ";", "\t"] = Field(
        title="Caractère séparateur de colonne",
        description="Par défaut une autodétéction est executée.",
        default="auto",
        json_schema_extra={
            "repr_type": "SegmentedControl",
            "repr_kwargs": {
                "options_labels": {"auto": "Auto", ",": "Virgule", ";": "Point-virgule", "\t": "Tabulation"},
            },
        },
    )
    decimal: Literal[".", ","] = Field(
        title="Caractère séparateur de décimal",
        description="Par défaut le point est utilisé.",
        default=".",
        json_schema_extra={
            "repr_type": "SegmentedControl",
            "repr_kwargs": {
                "options_labels": {".": "Point", ",": "Virgule"},
            },
        },
    )

# ---- Horaire CGN, profils inputs
CRUISES_NAME = Literal['Translemanique', 'Petit-Lac - Grand-Lac', 'Lavaux - Haut-Lac', 'Lavaux - Haut-Lac - Grand-Lac']
COURSES_NUMBER = {
    'Translemanique': [101, 106, 982, 983],
    'Petit-Lac - Grand-Lac': [102, 105, 388, 389],
    'Lavaux - Haut-Lac': [900, 903, 202, 905, 206, 207],
    'Lavaux - Haut-Lac - Grand-Lac': [904, 505, 506, 507, 508, 509, 9509, 487, 488],
}
ALL_COURSE_NUMBERS = sorted({n for courses in COURSES_NUMBER.values() for n in courses})

class NavParams(BaseModel):
    """
    Parametres du profil de navigation (MRUA)
    """
    acc: Quantity = Field(
        title="Accélération (strictement positive)",
        default_factory=lambda: Quantity(value=0.5, unit="m*s^-2"),
        json_schema_extra={
            "repr_type": "Quantity",
            "repr_kwargs": {
                "unit_options": {"m*s^-2": "m/s²"},
                "min": 0.01,
                **default_repr_kwargs,
            },
        },
    )
    dec: Quantity = Field(
        title="Décélération (strictement positive)",
        default_factory=lambda: Quantity(value=0.5, unit="m*s^-2"),
        json_schema_extra={
            "repr_type": "Quantity",
            "repr_kwargs": {
                "unit_options": {"m*s^-2": "m/s²"},
                "min": 0.01,
                **default_repr_kwargs,
            },
        },
    )
    v_croisiere: Quantity = Field(
        title="Vitesse de croisière (strictement positive)",
        description="Vitesse maximum du bateau (profil MRUA).",
        default_factory=lambda: Quantity(value=7.0, unit="m/s"),
        json_schema_extra={
            "repr_type": "Quantity",
            "repr_kwargs": {
                "unit_options": ["m/s", "km/h", "kn"],
                "min": 0.01,
                **default_repr_kwargs,
            },
        },
    )
    allow_delay: Literal["yes", "no"] = Field(
        title="Autoriser le rattrapage du retard",
        description="Si 'Oui', le profil peut rattraper un retard sur l'horaire cible.",
        default="yes",
        json_schema_extra={
            "repr_type": "SegmentedControl",
            "repr_kwargs": {
                "options_labels": {"yes": "Oui", "no": "Non"},
                "disabled": True,
            },
        },
    )

    @model_validator(mode="after")
    def check_positive_quantities(self):
        if float(self.acc.value) <= 0:
            raise ValueError("L'accélération doit être strictement positive.")
        if float(self.dec.value) <= 0:
            raise ValueError("La décélération doit être strictement positive.")
        if float(self.v_croisiere.value) <= 0:
            raise ValueError("La vitesse de croisière doit être strictement positive.")
        return self

class NavSpeedProfile(BaseModel):
    """
    Profil de vitesse construit à partir des horaires CGN
    Belle-Epoque - Haute saison 2025
    """
    id: str = Field(title="Nom", description="Nom/identifiant du profil de navigation.")
    select: Literal["cruise", "course"] = Field(
        title="Horaire CGN, par type - Haute saison 2025",
        description="Séléction de la catégorie du profil d'horaire à simuler.",
        default="cruise",
        json_schema_extra={
            "repr_type": "RadioItems",
            "repr_kwargs": {
                "options_labels": {"cruise": "Croisière CGN", "course": "Course CGN"}
            },
        },
    )
    cruise_name: CRUISES_NAME = Field(title="Nom de la croisière CGN - Haute saison 2025", description="Séléction du nom de la 'Croisière CGN' à simuler.")
    course_no: str | None = Field(
        title="Numéro de la course CGN - Haute saison 2025",
        description="Séléction du numéro de la 'Course CGN' à simuler.",
        default=None,
        json_schema_extra={"repr_kwargs": {"visible": ("select", "==", "course")}},
    )
    # unit: str = "m/s"
    # source: str = "all"
    params: NavParams = Field(
        title="Paramètres de vitesse de déplacement",
        default_factory=NavParams,
    )

    @model_validator(mode="after")
    def check_course_selection(self):
        if self.select == "course":
            if self.course_no is None:
                raise ValueError("Le champ 'course_no' est obligatoire quand 'Course CGN' est sélectionné.")
            try:
                course_no_int = int(self.course_no)
            except Exception as exc:  # noqa: BLE001
                raise ValueError("Le numéro de course doit être un entier valide.") from exc
            allowed = COURSES_NUMBER.get(self.cruise_name, [])
            if course_no_int not in allowed:
                raise ValueError(
                    f"Course {course_no_int} invalide pour la croisière '{self.cruise_name}'. "
                    f"Valeurs autorisées: {allowed}"
                )
            self.course_no = str(course_no_int)
        else:
            # En mode 'cruise', on ignore explicitement le numéro de course.
            self.course_no = None
        return self

