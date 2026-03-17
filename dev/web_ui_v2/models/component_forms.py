"""
Modeles Pydantic de formulaires UI V2 (lexique metier bateau).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UiFormBase(BaseModel):
    """
    Base commune pour les formulaires de creation de composants.
    """

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def ui_label(cls) -> str:
        return cls.__name__

    @classmethod
    def component_type(cls) -> str:
        raise NotImplementedError

    @classmethod
    def kind(cls) -> str:
        raise NotImplementedError

    def to_component(self) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_component(cls, component: dict[str, Any]) -> "UiFormBase":
        raise NotImplementedError


# Profiles
class ProfileConstantForm(UiFormBase):
    identifiant: str = Field(min_length=1, description="Nom du profil")
    unite: str = "W"
    valeur: float = 0.0
    master: bool = False

    @classmethod
    def ui_label(cls) -> str:
        return "Profil constant"

    @classmethod
    def component_type(cls) -> str:
        return "profile"

    @classmethod
    def kind(cls) -> str:
        return "constant"

    def to_component(self) -> dict[str, Any]:
        return {"id": self.identifiant, "kind": "constant", "unit": self.unite, "value": self.valeur, "master": self.master}

    @classmethod
    def from_component(cls, component: dict[str, Any]) -> "ProfileConstantForm":
        return cls(
            identifiant=str(component.get("id", "")),
            unite=str(component.get("unit", "W")),
            valeur=float(component.get("value", 0.0) or 0.0),
            master=bool(component.get("master", False)),
        )


class ProfileSeriesForm(UiFormBase):
    identifiant: str = Field(min_length=1)
    unite: str = "m/s"
    valeurs_csv: str = "0.0,1.0,2.0"
    master: bool = True

    @classmethod
    def ui_label(cls) -> str:
        return "Profil serie"

    @classmethod
    def component_type(cls) -> str:
        return "profile"

    @classmethod
    def kind(cls) -> str:
        return "series"

    def to_component(self) -> dict[str, Any]:
        values = [float(v.strip()) for v in self.valeurs_csv.split(",") if v.strip()]
        return {"id": self.identifiant, "kind": "series", "unit": self.unite, "data": values, "master": self.master}

    @classmethod
    def from_component(cls, component: dict[str, Any]) -> "ProfileSeriesForm":
        data = component.get("data", [])
        values = data if isinstance(data, list) else []
        values_csv = ",".join(str(v) for v in values)
        return cls(
            identifiant=str(component.get("id", "")),
            unite=str(component.get("unit", "m/s")),
            valeurs_csv=values_csv or "0.0,1.0,2.0",
            master=bool(component.get("master", True)),
        )


class ProfileFileForm(UiFormBase):
    identifiant: str = Field(min_length=1)
    unite: str = "m/s"
    chemin_fichier: str = ""
    colonne: str = ""
    separateur: str = ","
    decimal: str = "."
    encodage: str = "utf-8-sig"
    master: bool = True

    @classmethod
    def ui_label(cls) -> str:
        return "Profil depuis fichier CSV"

    @classmethod
    def component_type(cls) -> str:
        return "profile"

    @classmethod
    def kind(cls) -> str:
        return "file"

    def to_component(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.identifiant,
            "kind": "file",
            "unit": self.unite,
            "file": self.chemin_fichier,
            "decimal": self.decimal,
            "encoding": self.encodage,
            "master": self.master,
        }
        out["sep"] = self.separateur or ","
        out["column"] = self.colonne or None
        return out

    @classmethod
    def from_component(cls, component: dict[str, Any]) -> "ProfileFileForm":
        return cls(
            identifiant=str(component.get("id", "")),
            unite=str(component.get("unit", "m/s")),
            chemin_fichier=str(component.get("file", "")),
            colonne=str(component.get("column", "") or ""),
            separateur=str(component.get("sep", ",")),
            decimal=str(component.get("decimal", ".")),
            encodage=str(component.get("encoding", "utf-8-sig")),
            master=bool(component.get("master", True)),
        )


class ProfileNavSpeedForm(UiFormBase):
    identifiant: str = Field(min_length=1)
    unite: str = "m/s"
    source_nav: str = "cgn_croisieres/all"
    selection_mode: str = "cruise"
    cruise_name: str = "Lavaux - Haut-Lac"
    course_no: int = 0
    port_depart: str = ""
    port_arrivee: str = ""
    acc: float = 0.05
    dec: float = 0.05
    v_croisiere: float = 7.0
    allow_delay: bool = True
    master: bool = True

    @classmethod
    def ui_label(cls) -> str:
        return "Profil navigation CGN"

    @classmethod
    def component_type(cls) -> str:
        return "profile"

    @classmethod
    def kind(cls) -> str:
        return "nav_speed"

    def to_component(self) -> dict[str, Any]:
        select: dict[str, Any] = {"by": self.selection_mode}
        if self.selection_mode == "cruise":
            select["cruise_name"] = self.cruise_name
        elif self.selection_mode == "course":
            select["course_no"] = self.course_no
        elif self.selection_mode == "leg":
            select["leg"] = {"from_port": self.port_depart, "to_port": self.port_arrivee}
        return {
            "id": self.identifiant,
            "kind": "nav_speed",
            "unit": self.unite,
            "source": self.source_nav,
            "select": select,
            "params": {
                "acc": self.acc,
                "dec": self.dec,
                "v_croisiere": self.v_croisiere,
                "allow_delay": self.allow_delay,
            },
            "master": self.master,
        }

    @classmethod
    def from_component(cls, component: dict[str, Any]) -> "ProfileNavSpeedForm":
        select = component.get("select", {})
        params = component.get("params", {})
        leg = select.get("leg", {}) if isinstance(select, dict) else {}
        return cls(
            identifiant=str(component.get("id", "")),
            unite=str(component.get("unit", "m/s")),
            source_nav=str(component.get("source", "cgn_croisieres/all")),
            selection_mode=str(select.get("by", "cruise")) if isinstance(select, dict) else "cruise",
            cruise_name=str(select.get("cruise_name", "Lavaux - Haut-Lac")) if isinstance(select, dict) else "Lavaux - Haut-Lac",
            course_no=int(select.get("course_no", 0) or 0) if isinstance(select, dict) else 0,
            port_depart=str(leg.get("from_port", "")) if isinstance(leg, dict) else "",
            port_arrivee=str(leg.get("to_port", "")) if isinstance(leg, dict) else "",
            acc=float(params.get("acc", 0.05) or 0.05) if isinstance(params, dict) else 0.05,
            dec=float(params.get("dec", 0.05) or 0.05) if isinstance(params, dict) else 0.05,
            v_croisiere=float(params.get("v_croisiere", 7.0) or 7.0) if isinstance(params, dict) else 7.0,
            allow_delay=bool(params.get("allow_delay", True)) if isinstance(params, dict) else True,
            master=bool(component.get("master", True)),
        )


# Adapters
class AdapterSpeedToPowerPolyForm(UiFormBase):
    identifiant: str = Field(min_length=1)
    source_signal: str = ""
    coeffs_csv: str = "0.0"
    clip_min: float = 0.0
    unite_entree: str = "m/s"
    unite_sortie: str = "W"

    @classmethod
    def ui_label(cls) -> str:
        return "Adaptateur vitesse -> puissance (poly)"

    @classmethod
    def component_type(cls) -> str:
        return "adapter"

    @classmethod
    def kind(cls) -> str:
        return "speed_to_power_poly"

    def to_component(self) -> dict[str, Any]:
        coeffs = [float(v.strip()) for v in self.coeffs_csv.split(",") if v.strip()]
        return {
            "id": self.identifiant,
            "kind": "speed_to_power_poly",
            "source": self.source_signal,
            "unit_in": self.unite_entree,
            "unit_out": self.unite_sortie,
            "params": {"coeffs": coeffs, "clip_min": self.clip_min},
        }

    @classmethod
    def from_component(cls, component: dict[str, Any]) -> "AdapterSpeedToPowerPolyForm":
        params = component.get("params", {}) if isinstance(component.get("params"), dict) else {}
        coeffs = params.get("coeffs", [])
        coeffs_csv = ",".join(str(v) for v in coeffs) if isinstance(coeffs, list) else "0.0"
        return cls(
            identifiant=str(component.get("id", "")),
            source_signal=str(component.get("source", "")),
            coeffs_csv=coeffs_csv,
            clip_min=float(params.get("clip_min", 0.0) or 0.0),
            unite_entree=str(component.get("unit_in", "m/s")),
            unite_sortie=str(component.get("unit_out", "W")),
        )


class AdapterForceAndSpeedToPowerForm(UiFormBase):
    identifiant: str = Field(min_length=1)
    force_source: str = ""
    speed_source: str = ""
    force_unit_in: str = "N"
    speed_unit_in: str = "m/s"
    clip_min: float = 0.0
    unite_sortie: str = "W"

    @classmethod
    def ui_label(cls) -> str:
        return "Adaptateur force + vitesse -> puissance"

    @classmethod
    def component_type(cls) -> str:
        return "adapter"

    @classmethod
    def kind(cls) -> str:
        return "force_and_speed_to_power"

    def to_component(self) -> dict[str, Any]:
        return {
            "id": self.identifiant,
            "kind": "force_and_speed_to_power",
            "source": "",
            "unit_in": "",
            "unit_out": self.unite_sortie,
            "params": {
                "force_source": self.force_source,
                "speed_source": self.speed_source,
                "force_unit_in": self.force_unit_in,
                "speed_unit_in": self.speed_unit_in,
                "clip_min": self.clip_min,
            },
        }

    @classmethod
    def from_component(cls, component: dict[str, Any]) -> "AdapterForceAndSpeedToPowerForm":
        params = component.get("params", {}) if isinstance(component.get("params"), dict) else {}
        return cls(
            identifiant=str(component.get("id", "")),
            force_source=str(params.get("force_source", "")),
            speed_source=str(params.get("speed_source", "")),
            force_unit_in=str(params.get("force_unit_in", "N")),
            speed_unit_in=str(params.get("speed_unit_in", "m/s")),
            clip_min=float(params.get("clip_min", 0.0) or 0.0),
            unite_sortie=str(component.get("unit_out", "W")),
        )


class AdapterSpeedToForcePolyForm(UiFormBase):
    identifiant: str = Field(min_length=1)
    source_signal: str = ""
    coeffs_csv: str = "0.0"
    clip_min: float = 0.0
    unite_entree: str = "m/s"
    unite_sortie: str = "N"

    @classmethod
    def ui_label(cls) -> str:
        return "Adaptateur vitesse -> force (poly)"

    @classmethod
    def component_type(cls) -> str:
        return "adapter"

    @classmethod
    def kind(cls) -> str:
        return "speed_to_force_poly"

    def to_component(self) -> dict[str, Any]:
        coeffs = [float(v.strip()) for v in self.coeffs_csv.split(",") if v.strip()]
        return {
            "id": self.identifiant,
            "kind": "speed_to_force_poly",
            "source": self.source_signal,
            "unit_in": self.unite_entree,
            "unit_out": self.unite_sortie,
            "params": {"coeffs": coeffs, "clip_min": self.clip_min},
        }

    @classmethod
    def from_component(cls, component: dict[str, Any]) -> "AdapterSpeedToForcePolyForm":
        params = component.get("params", {}) if isinstance(component.get("params"), dict) else {}
        coeffs = params.get("coeffs", [])
        coeffs_csv = ",".join(str(v) for v in coeffs) if isinstance(coeffs, list) else "0.0"
        return cls(
            identifiant=str(component.get("id", "")),
            source_signal=str(component.get("source", "")),
            coeffs_csv=coeffs_csv,
            clip_min=float(params.get("clip_min", 0.0) or 0.0),
            unite_entree=str(component.get("unit_in", "m/s")),
            unite_sortie=str(component.get("unit_out", "N")),
        )


class AdapterSpeedToEtaPolyForm(UiFormBase):
    identifiant: str = Field(min_length=1)
    source_signal: str = ""
    coeffs_csv: str = "0.1,0.0,0.0,0.0"
    unite_entree: str = "m/s"
    unite_sortie: str = "-"

    @classmethod
    def ui_label(cls) -> str:
        return "Adaptateur vitesse -> rendement (poly)"

    @classmethod
    def component_type(cls) -> str:
        return "adapter"

    @classmethod
    def kind(cls) -> str:
        return "speed_to_eta_poly"

    def to_component(self) -> dict[str, Any]:
        coeffs = [float(v.strip()) for v in self.coeffs_csv.split(",") if v.strip()]
        return {
            "id": self.identifiant,
            "kind": "speed_to_eta_poly",
            "source": self.source_signal,
            "unit_in": self.unite_entree,
            "unit_out": self.unite_sortie,
            "params": {"coeffs": coeffs},
        }

    @classmethod
    def from_component(cls, component: dict[str, Any]) -> "AdapterSpeedToEtaPolyForm":
        params = component.get("params", {}) if isinstance(component.get("params"), dict) else {}
        coeffs = params.get("coeffs", [])
        coeffs_csv = ",".join(str(v) for v in coeffs) if isinstance(coeffs, list) else "0.1,0.0,0.0,0.0"
        return cls(
            identifiant=str(component.get("id", "")),
            source_signal=str(component.get("source", "")),
            coeffs_csv=coeffs_csv,
            unite_entree=str(component.get("unit_in", "m/s")),
            unite_sortie=str(component.get("unit_out", "-")),
        )


# Converters
class ConverterConstantEtaForm(UiFormBase):
    identifiant: str = Field(min_length=1)
    reseau_entree: str = "Chemical:fuel"
    reseau_sortie: str = "Electrical:main"
    rendement: float = 0.9

    @classmethod
    def ui_label(cls) -> str:
        return "Convertisseur a rendement constant"

    @classmethod
    def component_type(cls) -> str:
        return "converter"

    @classmethod
    def kind(cls) -> str:
        return "constant_eta"

    def to_component(self) -> dict[str, Any]:
        return {
            "id": self.identifiant,
            "kind": "constant_eta",
            "from_bus": self.reseau_entree,
            "to_bus": self.reseau_sortie,
            "params": {"eta": self.rendement},
        }

    @classmethod
    def from_component(cls, component: dict[str, Any]) -> "ConverterConstantEtaForm":
        params = component.get("params", {}) if isinstance(component.get("params"), dict) else {}
        return cls(
            identifiant=str(component.get("id", "")),
            reseau_entree=str(component.get("from_bus", "Chemical:fuel")),
            reseau_sortie=str(component.get("to_bus", "Electrical:main")),
            rendement=float(params.get("eta", 0.9) or 0.9),
        )


class ConverterVariableEtaForm(UiFormBase):
    identifiant: str = Field(min_length=1)
    reseau_entree: str = "Chemical:fuel"
    reseau_sortie: str = "Electrical:main"
    rendement_defaut: float = 1.0
    source_rendement: str = ""

    @classmethod
    def ui_label(cls) -> str:
        return "Convertisseur a rendement variable"

    @classmethod
    def component_type(cls) -> str:
        return "converter"

    @classmethod
    def kind(cls) -> str:
        return "variable_eta"

    def to_component(self) -> dict[str, Any]:
        eta_source = self.source_rendement.strip() or None
        return {
            "id": self.identifiant,
            "kind": "variable_eta",
            "from_bus": self.reseau_entree,
            "to_bus": self.reseau_sortie,
            "params": {"eta_default": self.rendement_defaut, "eta_source": eta_source},
        }

    @classmethod
    def from_component(cls, component: dict[str, Any]) -> "ConverterVariableEtaForm":
        params = component.get("params", {}) if isinstance(component.get("params"), dict) else {}
        return cls(
            identifiant=str(component.get("id", "")),
            reseau_entree=str(component.get("from_bus", "Chemical:fuel")),
            reseau_sortie=str(component.get("to_bus", "Electrical:main")),
            rendement_defaut=float(params.get("eta_default", 1.0) or 1.0),
            source_rendement=str(params.get("eta_source", "") or ""),
        )


class StorageDefaultForm(UiFormBase):
    identifiant: str = Field(min_length=1)
    bus_cible: str = "Chemical:fuel"
    vecteur: str = "diesel"

    @classmethod
    def ui_label(cls) -> str:
        return "Stockage (bilan energie)"

    @classmethod
    def component_type(cls) -> str:
        return "storage"

    @classmethod
    def kind(cls) -> str:
        return ""

    def to_component(self) -> dict[str, Any]:
        return {"id": self.identifiant, "bus": self.bus_cible, "vecteur": self.vecteur}

    @classmethod
    def from_component(cls, component: dict[str, Any]) -> "StorageDefaultForm":
        return cls(
            identifiant=str(component.get("id", "")),
            bus_cible=str(component.get("bus", "Chemical:fuel")),
            vecteur=str(component.get("vecteur", "diesel")),
        )


FORM_REGISTRY: dict[str, type[UiFormBase]] = {
    "profile.constant": ProfileConstantForm,
    "profile.series": ProfileSeriesForm,
    "profile.file": ProfileFileForm,
    "profile.nav_speed": ProfileNavSpeedForm,
    "adapter.speed_to_power_poly": AdapterSpeedToPowerPolyForm,
    "adapter.force_and_speed_to_power": AdapterForceAndSpeedToPowerForm,
    "adapter.speed_to_force_poly": AdapterSpeedToForcePolyForm,
    "adapter.speed_to_eta_poly": AdapterSpeedToEtaPolyForm,
    "converter.constant_eta": ConverterConstantEtaForm,
    "converter.variable_eta": ConverterVariableEtaForm,
    "storage.default": StorageDefaultForm,
}


def forms_for_component_type(component_type: str) -> list[tuple[str, type[UiFormBase]]]:
    prefix = f"{component_type}."
    out: list[tuple[str, type[UiFormBase]]] = []
    for key, model in FORM_REGISTRY.items():
        if key.startswith(prefix):
            out.append((key, model))
    return out


def model_for_key(form_key: str) -> type[UiFormBase] | None:
    return FORM_REGISTRY.get(form_key)


def infer_form_key(component_type: str, kind: str) -> str | None:
    raw_kind = (kind or "").strip()
    if component_type == "storage":
        return "storage.default"
    if not raw_kind:
        return None
    key = f"{component_type}.{raw_kind}"
    return key if key in FORM_REGISTRY else None
