# cgn_model/vessel_model/config.py

from typing import Literal, Any, Union, Annotated
from pydantic import BaseModel, StrictStr, ConfigDict, model_validator, field_validator, Field

type VesselType = Literal["DE", "steam", "undefined"]

class VesselCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: StrictStr
    vessel_type: VesselType

    @model_validator(mode="after")
    def check_fields(self):
        return self
    
# profiles
class ProfileCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    unit: StrictStr
    data: list[float] | None = None
    file: StrictStr | None = None

# adapters (discriminated union)
class PolyAdapterCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    kind: Literal["poly"]
    source: StrictStr
    unit_in: StrictStr
    unit_out: StrictStr
    params: dict[str, Any]
    @field_validator("params")
    @classmethod
    def check_poly(cls, v):
        if "coeffs" not in v or not isinstance(v["coeffs"], list):
            raise ValueError("params.coeffs requis (liste)")
        return v

AdapterCfg = Annotated[Union[PolyAdapterCfg], Field(discriminator="kind")]

# bindings input->bus
class InputBindCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    bus: StrictStr
    source: StrictStr  # id d’un profile OU d’un adapter
