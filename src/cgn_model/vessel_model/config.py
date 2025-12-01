# cgn_model/vessel_model/config.py

from typing import Literal, Any
from pydantic import BaseModel, StrictStr, ConfigDict, model_validator, Field

type VesselType = Literal["DE", "steam", "undefined"]

__all__ = ["VesselType", "VesselCfg", "ProfileCfg", "AdapterCfg", "InputBindCfg"]

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

# adapters
class AdapterCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    kind: StrictStr
    source: StrictStr
    unit_in: StrictStr
    unit_out: StrictStr
    params: dict[str, Any] = Field(default_factory=dict)

# bindings input->bus
class InputBindCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    bus: StrictStr
    source: StrictStr  # id d’un profile OU d’un adapter
