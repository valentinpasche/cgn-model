"""
Modeles Pydantic pour l'UI V2 orientee "bateau".
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ComponentType = Literal["profile", "adapter", "input", "converter", "storage"]
VesselType = Literal["DE", "steam", "undefined"]


class BrickTemplateModel(BaseModel):
    """
    Template de brique de bibliotheque.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    family: str = "General"
    component_type: ComponentType
    kind: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def _norm_name(cls, v: Any) -> str:
        s = str(v or "").strip()
        if not s:
            raise ValueError("Le nom du template est obligatoire.")
        return s


class BrickInstanceModel(BaseModel):
    """
    Instance de brique dans un schema assemble.
    """

    model_config = ConfigDict(extra="forbid")

    template_id: int
    instance_id: str
    source: str | None = None
    bus: str | None = None
    from_bus: str | None = None
    to_bus: str | None = None
    params_patch: dict[str, Any] = Field(default_factory=dict)

    @field_validator("instance_id", mode="before")
    @classmethod
    def _norm_instance_id(cls, v: Any) -> str:
        s = str(v or "").strip()
        if not s:
            raise ValueError("L'identifiant de l'instance est obligatoire.")
        return s


class BrickSchemaModel(BaseModel):
    """
    Schema de briques d'un bateau (version UI, sans YAML expose).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    vessel_name: str = "Bateau"
    vessel_type: VesselType = "DE"
    dt: float = Field(default=1.0, gt=0)
    instances: list[BrickInstanceModel] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def _norm_name(cls, v: Any) -> str:
        s = str(v or "").strip()
        if not s:
            raise ValueError("Le nom du schema est obligatoire.")
        return s
