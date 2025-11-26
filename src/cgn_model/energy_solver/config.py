# cgn_model/energy_solver/config.py

from typing import Any
from pydantic import BaseModel, Field, StrictStr, ConfigDict, model_validator
from cgn_model.energy_solver.types import Mode

__all__ = ["Cfg"]

# --- Solver ---
class SolverCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Mode

# --- Buses ---
class BusCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    carrier: StrictStr

# --- Inputs ---
class InputCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    bus: StrictStr

# --- Converters ---
class ConverterCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    from_bus: StrictStr
    to_bus: StrictStr
    kind: StrictStr
    params: dict[str, Any] = Field(default_factory=dict)


# --- Top-level ---
class Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    solver: SolverCfg
    buses: list[BusCfg]
    converters: list[ConverterCfg]
    inputs: list[InputCfg]

    @model_validator(mode="after")
    def cross_checks(self):
        bus_ids = {b.id for b in self.buses}

        bad_conv = [c.id for c in self.converters if c.from_bus not in bus_ids or c.to_bus not in bus_ids]
        bad_in   = [i.id for i in self.inputs if i.bus not in bus_ids]
        if bad_conv:
            raise ValueError(f"Convertisseurs référencent des bus inconnus: {bad_conv}")
        if bad_in:
            raise ValueError(f"Inputs référencent des bus inconnus: {bad_in}")

        from collections import Counter
        def dups(xs): return [k for k, v in Counter(xs).items() if v > 1]
        dup = dups([b.id for b in self.buses]) + dups([c.id for c in self.converters]) + dups([i.id for i in self.inputs])
        if dup:
            raise ValueError(f"IDs dupliqués: {dup}")

        return self
