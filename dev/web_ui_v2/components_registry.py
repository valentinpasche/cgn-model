"""Registry et helpers de gestion composants UI V2."""

from __future__ import annotations

from typing import Any

from dash import html
from dash_pydantic_form import ModelForm, fields
from pydantic import BaseModel

from components_basemodel import (
    ConstantEtaConverter,
    ForceAndSpeedToPowerAdapter,
    SpeedToForcePoly,
    SpeedToPowerPolyAdapter,
    VariableEtaConverter,
)
from services.storage import list_schemas, list_templates


TYPE_OPTIONS = [
    {"label": "Profil (signal entree)", "value": "profile"},
    {"label": "Adaptateur (transformateur signal)", "value": "adapter"},
    {"label": "Convertisseur puissance (watt)", "value": "converter"},
    {"label": "Stockage energie", "value": "storage"},
]

AIO_ID = "v2m-form"
FORM_ID = "main"

MODEL_SPECS: dict[str, dict[str, Any]] = {
    "converter.constant_eta": {
        "component_type": "converter",
        "kind": "constant_eta",
        "model": ConstantEtaConverter,
    },
    "converter.variable_eta": {
        "component_type": "converter",
        "kind": "variable_eta",
        "model": VariableEtaConverter,
    },
    "adapter.speed_to_power_poly": {
        "component_type": "adapter",
        "kind": "speed_to_power_poly",
        "model": SpeedToPowerPolyAdapter,
    },
    "adapter.force_and_speed_to_power": {
        "component_type": "adapter",
        "kind": "force_and_speed_to_power",
        "model": ForceAndSpeedToPowerAdapter,
    },
    "adapter.speed_to_force_poly": {
        "component_type": "adapter",
        "kind": "speed_to_force_poly",
        "model": SpeedToForcePoly,
    },
}


def first_doc_line(model_cls: type[BaseModel]) -> str:
    lines = (model_cls.__doc__ or "").strip().splitlines()
    return lines[0].strip() if lines else model_cls.__name__


def model_options(component_type: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for key, spec in MODEL_SPECS.items():
        if spec["component_type"] == component_type:
            out.append({"label": first_doc_line(spec["model"]), "value": key})
    return out


def default_model_key(component_type: str) -> str | None:
    opts = model_options(component_type)
    if not opts:
        return None
    return str(opts[0]["value"])


def fields_repr(model_key: str | None) -> dict[str, Any]:
    if model_key in {"adapter.speed_to_power_poly", "adapter.speed_to_force_poly"}:
        return {
            "coeffs": fields.List(
                render_type="scalar",
                n_cols="var(--pydf-form-cols)",
                wrapper_kwargs={"style": {"gridTemplateColumns": "repeat(5, minmax(0, 1fr))"}},
            )
        }
    return {}


def render_form(model_key: str | None, seed: dict[str, Any] | None):
    if not model_key or model_key not in MODEL_SPECS:
        return html.Div("Aucun modele pour ce type.")
    model_cls = MODEL_SPECS[model_key]["model"]
    item: Any = model_cls
    if isinstance(seed, dict) and seed:
        try:
            item = model_cls.model_validate(seed)
        except Exception:  # noqa: BLE001
            safe_seed = {k: v for k, v in seed.items() if k in model_cls.model_fields}
            item = model_cls.model_construct(**safe_seed)
    return ModelForm(item, AIO_ID, FORM_ID, debounce=200, form_cols=10, fields_repr=fields_repr(model_key))


def validate_form_data(model_key: str, form_data: dict[str, Any]) -> dict[str, Any]:
    model_cls = MODEL_SPECS[model_key]["model"]
    return model_cls.model_validate(form_data).model_dump(exclude_none=True)


def payload_from_data(model_key: str, raw: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    spec = MODEL_SPECS[model_key]
    ctype = str(spec["component_type"])
    kind = str(spec["kind"])

    if model_key == "converter.constant_eta":
        component = {
            "id": raw["id"],
            "kind": kind,
            "from_bus": raw.get("from_bus"),
            "to_bus": raw.get("to_bus"),
            "params": {"eta": raw["eta"]},
        }
    elif model_key == "converter.variable_eta":
        component = {
            "id": raw["id"],
            "kind": kind,
            "from_bus": raw.get("from_bus"),
            "to_bus": raw.get("to_bus"),
            "params": {"eta_default": 1.0, "eta_source": raw["eta_source"]},
        }
    elif model_key == "adapter.speed_to_power_poly":
        component = {
            "id": raw["id"],
            "kind": kind,
            "source": raw["source"],
            "unit_in": raw.get("unit_in", "m/s"),
            "unit_out": raw.get("unit_out", "W"),
            "params": {"coeffs": raw["coeffs"]},
        }
    elif model_key == "adapter.force_and_speed_to_power":
        component = {
            "id": raw["id"],
            "kind": kind,
            "source": "",
            "unit_in": "",
            "unit_out": raw.get("unit_out", "W"),
            "params": {
                "force_source": raw["force_source"],
                "speed_source": raw["speed_source"],
                "force_unit_in": raw.get("force_unit_in", "N"),
                "speed_unit_in": raw.get("speed_unit_in", "m/s"),
                "clip_min": 0.0,
            },
        }
    elif model_key == "adapter.speed_to_force_poly":
        component = {
            "id": raw["id"],
            "kind": kind,
            "source": raw["source"],
            "unit_in": raw.get("unit_in", "m/s"),
            "unit_out": raw.get("unit_out", "N"),
            "params": {"coeffs": raw["coeffs"]},
        }
    else:
        raise ValueError(f"Modele non supporte: {model_key}")

    return ctype, kind, {"component": component}


def seed_from_template(component_type: str, kind: str, payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    key = f"{component_type}.{kind}"
    if key not in MODEL_SPECS:
        return None, {}
    c = payload.get("component", {}) if isinstance(payload, dict) else {}
    p = c.get("params", {}) if isinstance(c.get("params"), dict) else {}

    if key == "converter.constant_eta":
        return key, {
            "id": c.get("id", ""),
            "from_bus": c.get("from_bus"),
            "to_bus": c.get("to_bus"),
            "eta": p.get("eta", 1.0),
        }
    if key == "converter.variable_eta":
        return key, {
            "id": c.get("id", ""),
            "from_bus": c.get("from_bus"),
            "to_bus": c.get("to_bus"),
            "eta_source": p.get("eta_source", ""),
        }
    if key == "adapter.speed_to_power_poly":
        return key, {
            "id": c.get("id", ""),
            "source": c.get("source", ""),
            "unit_in": c.get("unit_in", "m/s"),
            "unit_out": c.get("unit_out", "W"),
            "coeffs": p.get("coeffs", []),
        }
    if key == "adapter.force_and_speed_to_power":
        return key, {
            "id": c.get("id", ""),
            "force_source": p.get("force_source", ""),
            "speed_source": p.get("speed_source", ""),
            "force_unit_in": p.get("force_unit_in", "N"),
            "speed_unit_in": p.get("speed_unit_in", "m/s"),
            "unit_out": c.get("unit_out", "W"),
        }
    if key == "adapter.speed_to_force_poly":
        return key, {
            "id": c.get("id", ""),
            "source": c.get("source", ""),
            "unit_in": c.get("unit_in", "m/s"),
            "unit_out": c.get("unit_out", "N"),
            "coeffs": p.get("coeffs", []),
        }
    return None, {}


def local_rows(local_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(it.get("name", "")),
            "component_type": str(it.get("component_type", "")),
            "kind": str(it.get("kind", "")),
            "status": "local",
            "_scope": "local",
        }
        for it in local_items
    ]


def db_rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in list_templates():
        key = f'{r.get("component_type", "")}.{r.get("kind", "")}'
        if key not in MODEL_SPECS:
            continue
        out.append(
            {
                "name": str(r.get("name", "")),
                "component_type": str(r.get("component_type", "")),
                "kind": str(r.get("kind", "")),
                "status": "DB",
                "_scope": "db",
                "_db_id": int(r.get("id", 0)),
            }
        )
    return out


def mermaid_from_config(config: dict[str, Any] | None) -> str:
    cfg = config if isinstance(config, dict) else {}
    comps = cfg.get("components", [])
    lines = ["flowchart LR"]
    names = {str(c.get("name", "")) for c in comps if isinstance(c, dict)}
    if not names:
        return "flowchart LR\n  n0[Configuration vide]"

    for c in comps:
        if not isinstance(c, dict):
            continue
        n = str(c.get("name", "")).strip()
        if not n:
            continue
        ctype = str(c.get("component_type", ""))
        if ctype == "converter":
            lines.append(f'  {n}["{n}"]')
        elif ctype == "adapter":
            lines.append(f"  {n}{{{{{n}}}}}")
        elif ctype == "storage":
            lines.append(f"  {n}((({n})))")
        else:
            lines.append(f"  {n}[{n}]")

    for c in comps:
        if not isinstance(c, dict):
            continue
        dst = str(c.get("name", "")).strip()
        data = c.get("data", {})
        if not dst or not isinstance(data, dict):
            continue
        for src_key in ("source", "force_source", "speed_source", "eta_source", "from_bus"):
            src = str(data.get(src_key, "")).strip()
            if src and src in names:
                lines.append(f"  {src} --> {dst}")
        to_bus = str(data.get("to_bus", "")).strip()
        if to_bus and to_bus in names:
            lines.append(f"  {dst} --> {to_bus}")
    return "\n".join(lines)


def local_config_rows(local_cfgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(c.get("name", "")),
            "n_components": len(c.get("components", []) if isinstance(c.get("components"), list) else []),
            "status": "local",
            "_scope": "local",
        }
        for c in local_cfgs
    ]


def db_config_rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in list_schemas():
        schema = r.get("schema", {})
        n = len(schema.get("components", []) if isinstance(schema, dict) and isinstance(schema.get("components"), list) else [])
        out.append({"name": str(r.get("name", "")), "n_components": n, "status": "DB", "_scope": "db", "_db_id": int(r.get("id", 0))})
    return out
