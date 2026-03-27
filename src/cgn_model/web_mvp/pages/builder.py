"""
Builder guide: assemblage bloc par bloc depuis templates composants.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import yaml
from dash import Input, Output, State, callback, ctx, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate
from dash_extensions import Mermaid

from cgn_model.vessel_model import Vessel
from cgn_model.web_mvp.services.dag_mermaid import yaml_to_mermaid
from cgn_model.web_mvp.services.db import (
    get_component_template,
    get_vessel_config,
    list_component_templates,
    list_vessel_configs,
    upsert_vessel_config,
)

register_page(__name__, path="/builder", name="Builder")


SECTION_BY_TYPE = {
    "profile": "profiles",
    "adapter": "adapters",
    "input": "inputs",
    "converter": "converters",
    "storage": "storages",
}


def _new_blank_cfg() -> dict[str, Any]:
    return {
        "vessel": {"name": "New Vessel", "vessel_type": "undefined"},
        "simulation": {"dt": 1.0},
        "profiles": [],
        "adapters": [],
        "inputs": [],
        "solver": {"mode": "inverse"},
        "buses": [],
        "converters": [],
        "storages": [],
    }


def _config_options() -> list[dict[str, str | int]]:
    rows = list_vessel_configs()
    return [{"label": r.name, "value": r.id} for r in rows]


def _template_options() -> list[dict[str, str | int]]:
    rows = list_component_templates()
    return [{"label": f"{r.component_type} | {r.name}", "value": r.id} for r in rows]


def _infer_bus_carrier(bus_id: str) -> str:
    b = bus_id.lower()
    if "fuel" in b or "h2" in b or "diesel" in b or "chemical" in b:
        return "Chemical"
    if "shaft" in b or "mech" in b:
        return "Mechanical"
    return "Electrical"


def _ensure_buses(cfg: dict[str, Any]) -> None:
    existing = {str(b.get("id", "")): b for b in cfg.get("buses", []) if isinstance(b, dict)}
    required: set[str] = set()

    for inp in cfg.get("inputs", []):
        if isinstance(inp, dict):
            bus = str(inp.get("bus", "")).strip()
            if bus:
                required.add(bus)
    for conv in cfg.get("converters", []):
        if isinstance(conv, dict):
            fb = str(conv.get("from_bus", "")).strip()
            tb = str(conv.get("to_bus", "")).strip()
            if fb:
                required.add(fb)
            if tb:
                required.add(tb)
    for stor in cfg.get("storages", []):
        if isinstance(stor, dict):
            bus = str(stor.get("bus", "")).strip()
            if bus:
                required.add(bus)

    buses = cfg.setdefault("buses", [])
    for bid in sorted(required):
        if bid not in existing:
            buses.append({"id": bid, "carrier": _infer_bus_carrier(bid)})
            existing[bid] = buses[-1]


def _unique_component_id(cfg: dict[str, Any], candidate: str) -> str:
    used: set[str] = set()
    for section in ("profiles", "adapters", "inputs", "converters", "storages", "buses"):
        for item in cfg.get(section, []):
            if isinstance(item, dict):
                iid = str(item.get("id", "")).strip()
                if iid:
                    used.add(iid)
    base = candidate.strip() or "component"
    if base not in used:
        return base
    idx = 2
    while f"{base}_{idx}" in used:
        idx += 1
    return f"{base}_{idx}"


def _component_rows(cfg: dict[str, Any]) -> list[html.Tr]:
    rows: list[html.Tr] = []
    for ctype, section in SECTION_BY_TYPE.items():
        for item in cfg.get(section, []):
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id", ""))
            kind = str(item.get("kind", ""))
            rows.append(html.Tr([html.Td(ctype), html.Td(cid), html.Td(kind)]))
    if not rows:
        return [html.Tr([html.Td("Aucun composant dans le builder.")])]
    return rows


def _component_option_payload(cfg: dict[str, Any]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for ctype, section in SECTION_BY_TYPE.items():
        for idx, item in enumerate(cfg.get(section, [])):
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id", f"{section}_{idx}"))
            options.append(
                {
                    "label": f"{ctype} | {cid}",
                    "value": json.dumps({"section": section, "index": idx}),
                }
            )
    return options


def _dump_yaml(cfg: dict[str, Any]) -> str:
    return yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)


layout = html.Div(
    [
        html.H3("Builder guide"),
        html.P("Assembler des briques depuis la bibliotheque composants, puis valider et sauvegarder la configuration."),
        dcc.Interval(id="builder-onload-refresh", interval=200, n_intervals=0, max_intervals=1),
        dcc.Store(id="builder-cfg-store", data=_new_blank_cfg()),
        html.Div(
            [
                html.Div(
                    [
                        html.H4("Sources"),
                        html.Label("Configuration existante"),
                        dcc.Dropdown(id="builder-config-select", options=_config_options()),
                        html.Div(
                            [
                                html.Button("Charger config", id="builder-load-config", n_clicks=0),
                                html.Button("Nouvelle config", id="builder-new-config", n_clicks=0, style={"marginLeft": "8px"}),
                                html.Button("Rafraichir listes", id="builder-refresh-sources", n_clicks=0, style={"marginLeft": "8px"}),
                            ],
                            style={"marginTop": "8px"},
                        ),
                        html.H4("Ajouter une brique", style={"marginTop": "16px"}),
                        dcc.Dropdown(id="builder-template-select", options=_template_options()),
                        html.Button("Ajouter au build", id="builder-add-template", n_clicks=0, style={"marginTop": "8px"}),
                        html.H4("Editer liaisons", style={"marginTop": "16px"}),
                        dcc.Dropdown(id="builder-link-select", placeholder="Choisir un composant du build"),
                        html.Div(
                            [
                                html.Div([html.Label("source"), dcc.Input(id="builder-link-source", type="text", style={"width": "100%"})], style={"width": "49%"}),
                                html.Div([html.Label("bus"), dcc.Input(id="builder-link-bus", type="text", style={"width": "100%"})], style={"width": "49%"}),
                            ],
                            style={"display": "flex", "gap": "2%"},
                        ),
                        html.Div(
                            [
                                html.Div([html.Label("from_bus"), dcc.Input(id="builder-link-from-bus", type="text", style={"width": "100%"})], style={"width": "49%"}),
                                html.Div([html.Label("to_bus"), dcc.Input(id="builder-link-to-bus", type="text", style={"width": "100%"})], style={"width": "49%"}),
                            ],
                            style={"display": "flex", "gap": "2%", "marginTop": "6px"},
                        ),
                        html.Div(
                            [
                                html.Button("Appliquer liaisons", id="builder-apply-links", n_clicks=0),
                                html.Button(
                                    "Supprimer composant selectionne",
                                    id="builder-delete-component",
                                    n_clicks=0,
                                    style={"marginLeft": "8px"},
                                ),
                            ],
                            style={"marginTop": "8px"},
                        ),
                        html.H4("Sauvegarde et validation", style={"marginTop": "16px"}),
                        dcc.Input(id="builder-save-name", type="text", placeholder="Nom configuration", style={"width": "100%"}),
                        html.Div(
                            [
                                html.Button("Valider modele", id="builder-validate", n_clicks=0),
                                html.Button("Sauver configuration", id="builder-save-config", n_clicks=0, style={"marginLeft": "8px"}),
                            ],
                            style={"marginTop": "8px"},
                        ),
                        html.Div(id="builder-status", style={"marginTop": "10px"}),
                        html.Div(id="builder-validate-status", style={"marginTop": "6px", "fontWeight": 600}),
                    ],
                    style={"width": "34%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px"},
                ),
                html.Div(
                    [
                        html.H4("Apercu Mermaid"),
                        Mermaid(id="builder-mermaid-chart", chart="flowchart LR\n  a[no_data]"),
                        html.H4("Composants en cours", style={"marginTop": "12px"}),
                        html.Table(
                            [
                                html.Thead(html.Tr([html.Th("Type"), html.Th("ID"), html.Th("Kind")])),
                                html.Tbody(id="builder-comp-table"),
                            ],
                            style={"width": "100%"},
                        ),
                        html.H4("YAML final", style={"marginTop": "12px"}),
                        dcc.Textarea(
                            id="builder-yaml",
                            readOnly=True,
                            style={"width": "100%", "height": "360px", "fontFamily": "Consolas, monospace"},
                        ),
                    ],
                    style={"width": "64%", "border": "1px solid #ddd", "borderRadius": "8px", "padding": "10px"},
                ),
            ],
            style={"display": "flex", "gap": "2%"},
        ),
        html.Div(style={"height": "120px"}),
    ]
)


@callback(
    Output("builder-config-select", "options"),
    Output("builder-template-select", "options"),
    Input("builder-onload-refresh", "n_intervals"),
    Input("builder-refresh-sources", "n_clicks"),
)
def refresh_sources(_: int, __: int):
    return _config_options(), _template_options()


@callback(
    Output("builder-cfg-store", "data"),
    Output("builder-save-name", "value"),
    Output("builder-status", "children"),
    Input("builder-new-config", "n_clicks"),
    Input("builder-load-config", "n_clicks"),
    State("builder-config-select", "value"),
    prevent_initial_call=True,
)
def load_or_new_builder(new_clicks: int, load_clicks: int, selected_id: int | None):
    triggered = ctx.triggered_id
    if triggered == "builder-new-config":
        return _new_blank_cfg(), "", "Nouveau builder initialise."
    if triggered == "builder-load-config":
        if selected_id is None:
            return no_update, no_update, "Selectionne une configuration a charger."
        row = get_vessel_config(int(selected_id))
        if row is None:
            return no_update, no_update, "Configuration introuvable."
        try:
            cfg = yaml.safe_load(row.yaml_text)
            if not isinstance(cfg, dict):
                raise ValueError("YAML invalide.")
            _ensure_buses(cfg)
            return cfg, row.name, f"Configuration chargee dans le builder: {row.name}"
        except Exception as exc:  # noqa: BLE001
            return no_update, no_update, f"Erreur chargement config: {exc}"
    raise PreventUpdate


@callback(
    Output("builder-cfg-store", "data", allow_duplicate=True),
    Output("builder-status", "children", allow_duplicate=True),
    Input("builder-add-template", "n_clicks"),
    State("builder-template-select", "value"),
    State("builder-cfg-store", "data"),
    prevent_initial_call=True,
)
def add_template_to_builder(_: int, template_id: int | None, cfg: dict[str, Any]):
    if template_id is None:
        return no_update, "Selectionne un template composant."
    row = get_component_template(int(template_id))
    if row is None:
        return no_update, "Template introuvable."

    next_cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else _new_blank_cfg()
    payload = row.payload.get("component", row.payload)
    if not isinstance(payload, dict):
        payload = {}
    component = copy.deepcopy(payload)
    section = SECTION_BY_TYPE.get(row.component_type)
    if section is None:
        return no_update, f"Type template non supporte: {row.component_type}"

    candidate = str(component.get("id", "")).strip() or row.name
    component["id"] = _unique_component_id(next_cfg, candidate)

    if row.component_type == "profile":
        component.setdefault("kind", row.kind)
        component.setdefault("unit", "W")
        if component.get("kind") == "constant":
            component.setdefault("value", 0.0)
        if component.get("kind") == "series":
            component.setdefault("data", [0.0])
    elif row.component_type == "adapter":
        component.setdefault("kind", row.kind)
        component.setdefault("source", "")
        component.setdefault("unit_in", "W")
        component.setdefault("unit_out", "W")
        component.setdefault("params", {})
    elif row.component_type == "input":
        component.setdefault("source", "")
        component.setdefault("bus", "")
        component.setdefault("sign", "consume")
    elif row.component_type == "converter":
        component.setdefault("kind", row.kind)
        component.setdefault("from_bus", "")
        component.setdefault("to_bus", "")
        component.setdefault("params", {})
    elif row.component_type == "storage":
        component.setdefault("bus", "")

    next_cfg.setdefault(section, []).append(component)
    _ensure_buses(next_cfg)
    return next_cfg, f"Template ajoute: {row.name} -> {component['id']}"


@callback(
    Output("builder-cfg-store", "data", allow_duplicate=True),
    Output("builder-status", "children", allow_duplicate=True),
    Input("builder-apply-links", "n_clicks"),
    State("builder-link-select", "value"),
    State("builder-link-source", "value"),
    State("builder-link-bus", "value"),
    State("builder-link-from-bus", "value"),
    State("builder-link-to-bus", "value"),
    State("builder-cfg-store", "data"),
    prevent_initial_call=True,
)
def apply_component_links(
    _: int,
    selection_payload: str | None,
    source: str | None,
    bus: str | None,
    from_bus: str | None,
    to_bus: str | None,
    cfg: dict[str, Any],
):
    if not selection_payload:
        return no_update, "Selectionne un composant a editer."
    try:
        sel = json.loads(selection_payload)
        section = str(sel["section"])
        index = int(sel["index"])
    except Exception as exc:  # noqa: BLE001
        return no_update, f"Selection invalide: {exc}"

    next_cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else _new_blank_cfg()
    section_items = next_cfg.get(section, [])
    if not isinstance(section_items, list) or index < 0 or index >= len(section_items):
        return no_update, "Composant selectionne introuvable dans le builder."
    item = section_items[index]
    if not isinstance(item, dict):
        return no_update, "Composant invalide."

    if source is not None:
        src = source.strip()
        if src:
            item["source"] = src
    if bus is not None:
        b = bus.strip()
        if b:
            item["bus"] = b
    if from_bus is not None:
        fb = from_bus.strip()
        if fb:
            item["from_bus"] = fb
    if to_bus is not None:
        tb = to_bus.strip()
        if tb:
            item["to_bus"] = tb

    _ensure_buses(next_cfg)
    return next_cfg, f"Liaisons mises a jour pour {item.get('id','component')}."


@callback(
    Output("builder-cfg-store", "data", allow_duplicate=True),
    Output("builder-status", "children", allow_duplicate=True),
    Input("builder-delete-component", "n_clicks"),
    State("builder-link-select", "value"),
    State("builder-cfg-store", "data"),
    prevent_initial_call=True,
)
def delete_selected_component(_: int, selection_payload: str | None, cfg: dict[str, Any]):
    if not selection_payload:
        return no_update, "Selectionne un composant a supprimer."
    try:
        sel = json.loads(selection_payload)
        section = str(sel["section"])
        index = int(sel["index"])
    except Exception as exc:  # noqa: BLE001
        return no_update, f"Selection invalide: {exc}"

    next_cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else _new_blank_cfg()
    section_items = next_cfg.get(section, [])
    if not isinstance(section_items, list) or index < 0 or index >= len(section_items):
        return no_update, "Composant selectionne introuvable."
    item = section_items.pop(index)
    _ensure_buses(next_cfg)
    return next_cfg, f"Composant supprime: {item.get('id','component')}."


@callback(
    Output("builder-status", "children", allow_duplicate=True),
    Input("builder-save-config", "n_clicks"),
    State("builder-save-name", "value"),
    State("builder-cfg-store", "data"),
    prevent_initial_call=True,
)
def save_builder_config(_: int, cfg_name: str | None, cfg: dict[str, Any]):
    raw_name = (cfg_name or "").strip()
    if not raw_name:
        return "Donne un nom de configuration avant sauvegarde."
    try:
        yaml_text = _dump_yaml(cfg)
        upsert_vessel_config(raw_name, yaml_text)
        return f"Configuration sauvegardee: {raw_name}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur sauvegarde config: {exc}"


@callback(
    Output("builder-validate-status", "children"),
    Input("builder-validate", "n_clicks"),
    State("builder-cfg-store", "data"),
    prevent_initial_call=True,
)
def validate_builder_cfg(_: int, cfg: dict[str, Any]):
    try:
        Vessel.from_yaml(cfg)
        return "Validation OK (Vessel.from_yaml)"
    except Exception as exc:  # noqa: BLE001
        return f"Validation KO: {exc}"


@callback(
    Output("builder-mermaid-chart", "chart"),
    Output("builder-yaml", "value"),
    Output("builder-comp-table", "children"),
    Output("builder-link-select", "options"),
    Input("builder-cfg-store", "data"),
)
def render_builder(cfg: dict[str, Any]):
    if not isinstance(cfg, dict):
        cfg = _new_blank_cfg()
    try:
        chart = yaml_to_mermaid(cfg)
    except Exception as exc:  # noqa: BLE001
        err = str(exc).replace('"', "'")
        chart = f'flowchart LR\n  err["Erreur Mermaid: {err}"]'
    yaml_text = _dump_yaml(cfg)
    rows = _component_rows(cfg)
    options = _component_option_payload(cfg)
    return chart, yaml_text, rows, options
