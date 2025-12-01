# cgn_model/vessel_model/config.py

from typing import Literal
from pydantic import BaseModel, StrictStr, ConfigDict, model_validator

type VesselType = Literal["DE", "steam", "undefined"]

class VesselCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: StrictStr
    vessel_type: VesselType

    @model_validator(mode="after")
    def check_fields(self):
        return self