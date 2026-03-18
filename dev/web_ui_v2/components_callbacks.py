"""Callbacks UI V2 composants."""

from __future__ import annotations

from typing import Any

from dash import Input, Output, State, ctx, no_update
from dash_pydantic_form import ModelForm
from pydantic import ValidationError

from components_registry import (
    AIO_ID,
    FORM_ID,
    db_config_rows,
    db_rows,
    default_model_key,
    local_rows,
    local_config_rows,
    mermaid_from_config,
    model_options,
    payload_from_data,
    render_form,
    seed_from_template,
    validate_form_data,
)
from services.storage import delete_template, get_template_by_name, list_schemas, upsert_schema, upsert_template


def register_callbacks(app):
    @app.callback(
        Output("v2cfg-save-name", "value"),
        Input("v2cfg-current", "data"),
    )
    def cfg_name_reflect(current_cfg: dict[str, Any] | None):
        current = current_cfg if isinstance(current_cfg, dict) else {}
        return str(current.get("name", "config_local"))

    @app.callback(
        Output("v2cfg-save-choice", "style"),
        Input("v2cfg-save", "n_clicks"),
        Input("v2cfg-save-cancel", "n_clicks"),
        Input("v2cfg-save-local", "n_clicks"),
        Input("v2cfg-save-db", "n_clicks"),
        prevent_initial_call=True,
    )
    def cfg_toggle_save_choice(_: int, __: int, ___: int, ____: int):
        if ctx.triggered_id == "v2cfg-save":
            return {"display": "block", "marginBottom": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"}
        return {"display": "none", "marginBottom": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"}

    @app.callback(
        Output("v2m-components-table", "data"),
        Input("v2m-refresh", "n_intervals"),
        Input("v2m-local-components", "data"),
        Input("v2m-save-db", "n_clicks"),
        Input("v2m-update-yes", "n_clicks"),
        Input("v2m-delete-yes", "n_clicks"),
    )
    def refresh_table(_: int, local_items: list[dict[str, Any]] | None, __: int, ___: int, ____: int):
        return local_rows(list(local_items or [])) + db_rows()

    @app.callback(
        Output("v2cfg-add-component", "options"),
        Output("v2cfg-remove-component", "options"),
        Output("v2cfg-select", "options"),
        Output("v2cfg-table", "data"),
        Output("v2cfg-mermaid", "chart"),
        Input("v2m-local-components", "data"),
        Input("v2cfg-current", "data"),
        Input("v2cfg-local-configs", "data"),
        Input("v2cfg-conflict-yes", "n_clicks"),
        Input("v2cfg-save-db", "n_clicks"),
    )
    def cfg_refresh(local_items: list[dict[str, Any]] | None, current_cfg: dict[str, Any] | None, local_cfgs: list[dict[str, Any]] | None, _: int, __: int):
        local_items = list(local_items or [])
        current = current_cfg if isinstance(current_cfg, dict) else {"name": "config_local", "components": []}
        comps = current.get("components", [])
        add_opts = [{"label": str(c.get("name", "")), "value": str(c.get("name", ""))} for c in local_items if str(c.get("name", "")).strip()]
        rem_opts = [{"label": str(c.get("name", "")), "value": str(c.get("name", ""))} for c in comps if isinstance(c, dict) and str(c.get("name", "")).strip()]
        cfg_rows = local_config_rows(list(local_cfgs or [])) + db_config_rows()
        cfg_opts = [{"label": f'{r.get("name", "")} [{r.get("status", "")}]', "value": f'{r.get("_scope","")}|{r.get("name","")}' } for r in cfg_rows]
        return add_opts, rem_opts, cfg_opts, cfg_rows, mermaid_from_config(current)

    @app.callback(
        Output("v2cfg-current", "data"),
        Output("v2cfg-status", "children"),
        Input("v2cfg-add-btn", "n_clicks"),
        State("v2cfg-add-component", "value"),
        State("v2m-local-components", "data"),
        State("v2cfg-current", "data"),
        prevent_initial_call=True,
    )
    def cfg_add_component(_: int, comp_name: str | None, local_items: list[dict[str, Any]] | None, current_cfg: dict[str, Any] | None):
        if not comp_name:
            return no_update, "Selectionne un composant local a ajouter."
        current = current_cfg if isinstance(current_cfg, dict) else {"name": "config_local", "components": []}
        items = list(local_items or [])
        found = next((x for x in items if str(x.get("name", "")) == str(comp_name)), None)
        if found is None:
            return no_update, "Composant local introuvable."
        comps = [c for c in current.get("components", []) if isinstance(c, dict)]
        if any(str(c.get("name", "")) == str(comp_name) for c in comps):
            return no_update, f"Le composant '{comp_name}' est deja dans la config."
        comps.append(found)
        current["components"] = comps
        return current, f"Composant ajoute: {comp_name}"

    @app.callback(
        Output("v2cfg-current", "data", allow_duplicate=True),
        Output("v2cfg-status", "children", allow_duplicate=True),
        Input("v2cfg-remove-btn", "n_clicks"),
        State("v2cfg-remove-component", "value"),
        State("v2cfg-current", "data"),
        prevent_initial_call=True,
    )
    def cfg_remove_component(_: int, comp_name: str | None, current_cfg: dict[str, Any] | None):
        if not comp_name:
            return no_update, "Selectionne un composant a supprimer."
        current = current_cfg if isinstance(current_cfg, dict) else {"name": "config_local", "components": []}
        comps = [c for c in current.get("components", []) if isinstance(c, dict)]
        new_comps = [c for c in comps if str(c.get("name", "")) != str(comp_name)]
        current["components"] = new_comps
        return current, f"Composant supprime: {comp_name}"

    @app.callback(
        Output("v2cfg-current", "data", allow_duplicate=True),
        Output("v2cfg-pending-load", "data"),
        Output("v2cfg-conflict-modal", "opened"),
        Output("v2cfg-status", "children", allow_duplicate=True),
        Output("v2m-local-components", "data", allow_duplicate=True),
        Input("v2cfg-load", "n_clicks"),
        State("v2cfg-select", "value"),
        State("v2cfg-local-configs", "data"),
        State("v2m-local-components", "data"),
        prevent_initial_call=True,
    )
    def cfg_load(_: int, selected: str | None, local_cfgs: list[dict[str, Any]] | None, local_items: list[dict[str, Any]] | None):
        if not selected or "|" not in selected:
            return no_update, no_update, False, "Selectionne une configuration.", no_update
        scope, name = selected.split("|", 1)
        cfg: dict[str, Any] | None = None
        if scope == "local":
            cfg = next((c for c in (local_cfgs or []) if str(c.get("name", "")) == name), None)
        else:
            row = next((r for r in list_schemas() if str(r.get("name", "")) == name), None)
            cfg = row.get("schema", {}) if isinstance(row, dict) else None
        if not isinstance(cfg, dict):
            return no_update, no_update, False, "Configuration introuvable.", no_update
        cfg_comps = [c for c in cfg.get("components", []) if isinstance(c, dict)]
        local_map = {str(i.get("name", "")): i for i in (local_items or [])}
        conflicts = [str(c.get("name", "")) for c in cfg_comps if str(c.get("name", "")) in local_map]
        if conflicts:
            pending = {"config": cfg, "conflicts": conflicts}
            return no_update, pending, True, f"Conflits detectes: {', '.join(conflicts)}", no_update
        merged = list(local_items or [])
        existing = {str(i.get("name", "")) for i in merged}
        for c in cfg_comps:
            n = str(c.get("name", ""))
            if n and n not in existing:
                merged.append(c)
        return cfg, {}, False, f"Configuration chargee: {name}", merged

    @app.callback(
        Output("v2cfg-current", "data", allow_duplicate=True),
        Output("v2m-local-components", "data", allow_duplicate=True),
        Output("v2cfg-conflict-modal", "opened", allow_duplicate=True),
        Output("v2cfg-pending-load", "data", allow_duplicate=True),
        Output("v2cfg-status", "children", allow_duplicate=True),
        Input("v2cfg-conflict-yes", "n_clicks"),
        State("v2cfg-pending-load", "data"),
        State("v2m-local-components", "data"),
        prevent_initial_call=True,
    )
    def cfg_conflict_yes(_: int, pending: dict[str, Any] | None, local_items: list[dict[str, Any]] | None):
        if not isinstance(pending, dict) or not pending:
            return no_update, no_update, False, {}, "Aucun chargement en attente."
        cfg = pending.get("config", {})
        comps = [c for c in cfg.get("components", []) if isinstance(c, dict)]
        merged = {str(i.get("name", "")): i for i in (local_items or [])}
        for c in comps:
            n = str(c.get("name", ""))
            if n:
                merged[n] = c
        return cfg, list(merged.values()), False, {}, "Configuration chargee avec ecrasement local."

    @app.callback(
        Output("v2cfg-conflict-modal", "opened", allow_duplicate=True),
        Output("v2cfg-pending-load", "data", allow_duplicate=True),
        Output("v2cfg-status", "children", allow_duplicate=True),
        Input("v2cfg-conflict-no", "n_clicks"),
        prevent_initial_call=True,
    )
    def cfg_conflict_no(_: int):
        return False, {}, "Chargement annule."

    @app.callback(
        Output("v2cfg-local-configs", "data"),
        Output("v2cfg-status", "children", allow_duplicate=True),
        Input("v2cfg-save-local", "n_clicks"),
        State("v2cfg-current", "data"),
        State("v2cfg-local-configs", "data"),
        State("v2cfg-save-name", "value"),
        prevent_initial_call=True,
    )
    def cfg_save_local(_: int, current_cfg: dict[str, Any] | None, local_cfgs: list[dict[str, Any]] | None, save_name: str | None):
        cfg = current_cfg if isinstance(current_cfg, dict) else {}
        name = str(save_name or cfg.get("name", "config_local")).strip() or "config_local"
        cfg["name"] = name
        arr = [c for c in (local_cfgs or []) if str(c.get("name", "")) != name]
        arr.append(cfg)
        return arr, f"Configuration locale sauvegardee: {name}"

    @app.callback(
        Output("v2cfg-current", "data", allow_duplicate=True),
        Output("v2cfg-status", "children", allow_duplicate=True),
        Input("v2cfg-save-db", "n_clicks"),
        State("v2cfg-current", "data"),
        State("v2cfg-save-name", "value"),
        prevent_initial_call=True,
    )
    def cfg_save_db(_: int, current_cfg: dict[str, Any] | None, save_name: str | None):
        cfg = current_cfg if isinstance(current_cfg, dict) else {}
        name = str(save_name or cfg.get("name", "config_local")).strip() or "config_local"
        cfg["name"] = name
        upsert_schema(name, cfg)
        return cfg, f"Configuration sauvegardee en DB: {name}"

    @app.callback(
        Output("v2cfg-status", "children", allow_duplicate=True),
        Input("v2cfg-validate", "n_clicks"),
        State("v2cfg-current", "data"),
        prevent_initial_call=True,
    )
    def cfg_validate(_: int, current_cfg: dict[str, Any] | None):
        cfg = current_cfg if isinstance(current_cfg, dict) else {}
        comps = [c for c in cfg.get("components", []) if isinstance(c, dict)]
        if not comps:
            return "Validation echec: configuration vide."
        names = {str(c.get("name", "")) for c in comps}
        incoming = {n: 0 for n in names}
        outgoing = {n: 0 for n in names}
        for c in comps:
            n = str(c.get("name", ""))
            d = c.get("data", {})
            if not isinstance(d, dict):
                continue
            for k in ("source", "force_source", "speed_source", "eta_source", "from_bus"):
                src = str(d.get(k, ""))
                if src in names and n in names:
                    incoming[n] += 1
                    outgoing[src] += 1
            to_bus = str(d.get("to_bus", ""))
            if to_bus in names and n in names:
                incoming[to_bus] += 1
                outgoing[n] += 1
        isolated = [n for n in names if incoming.get(n, 0) == 0 and outgoing.get(n, 0) == 0]
        if isolated:
            return f"Validation echec: composants isoles -> {', '.join(sorted(isolated))}"
        return "Validation OK: liaisons minimales coherentes."

    @app.callback(
        Output("v2m-select", "options"),
        Input("v2m-components-table", "data"),
    )
    def selector_options(rows: list[dict[str, Any]] | None):
        out: list[dict[str, str]] = []
        for r in (rows or []):
            name = str(r.get("name", "")).strip()
            scope = str(r.get("_scope", "")).strip()
            status = str(r.get("status", "")).strip()
            if not name or not scope:
                continue
            out.append({"label": f"{name} [{status}]", "value": f"{scope}|{name}"})
        return out

    @app.callback(
        Output("v2m-model", "options"),
        Output("v2m-model", "value"),
        Input("v2m-type", "value"),
    )
    def update_model_options(component_type: str):
        ctype = component_type or "converter"
        return model_options(ctype), default_model_key(ctype)

    @app.callback(
        Output("v2m-form-container", "children"),
        Input("v2m-model", "value"),
        Input("v2m-form-seed", "data"),
    )
    def render_form_cb(model_key: str | None, seed: dict[str, Any] | None):
        return render_form(model_key, seed if isinstance(seed, dict) else {})

    @app.callback(
        Output("v2m-type", "value", allow_duplicate=True),
        Output("v2m-model", "value", allow_duplicate=True),
        Output("v2m-form-seed", "data", allow_duplicate=True),
        Output("v2m-status", "children", allow_duplicate=True),
        Input("v2m-load-edit", "n_clicks"),
        State("v2m-components-table", "data"),
        State("v2m-local-components", "data"),
        State("v2m-select", "value"),
        prevent_initial_call=True,
    )
    def load_edit(_: int, rows: list[dict[str, Any]] | None, local_items: list[dict[str, Any]] | None, selected_value: str | None):
        if not rows or not selected_value or "|" not in selected_value:
            return no_update, no_update, no_update, "Selectionne un composant a editer."

        scope, name = selected_value.split("|", 1)
        row = next((r for r in rows if str(r.get("_scope", "")) == scope and str(r.get("name", "")) == name), None)
        if row is None:
            return no_update, no_update, no_update, "Selection invalide."

        ctype = str(row.get("component_type", ""))
        kind = str(row.get("kind", ""))
        model_key = f"{ctype}.{kind}"

        if scope == "local":
            local_map = {(str(it.get("name", "")), str(it.get("component_type", "")), str(it.get("kind", ""))): it for it in (local_items or [])}
            item = local_map.get((name, ctype, kind), {})
            seed = item.get("data", {}) if isinstance(item, dict) else {}
        else:
            t = get_template_by_name(name)
            if t is None:
                return no_update, no_update, no_update, "Composant DB introuvable."
            model_key, seed = seed_from_template(ctype, kind, t.get("payload", {}))
            if model_key is None:
                return no_update, no_update, no_update, "Type/Kind non supporte par ce formulaire."

        return ctype, model_key, seed, f"Edition chargee: {name}"

    @app.callback(
        Output("v2m-status", "children"),
        Input("v2m-validate", "n_clicks"),
        State("v2m-model", "value"),
        State(ModelForm.ids.main(AIO_ID, FORM_ID), "data"),
        State("v2m-components-table", "data"),
        prevent_initial_call=True,
    )
    def validate(_: int, model_key: str | None, form_data: dict[str, Any] | None, rows: list[dict[str, Any]] | None):
        if not model_key:
            return "Choisis un modele."
        if not isinstance(form_data, dict):
            return "Formulaire vide."
        try:
            raw = validate_form_data(model_key, form_data)
            name = str(raw.get("id", "")).strip()
            if not name:
                return "Erreur validation: nom requis."
            all_names = {str(r.get("name", "")).strip() for r in (rows or [])}
            if name in all_names:
                return f"Attention: le nom '{name}' existe deja."
            return "Validation OK."
        except ValidationError as exc:
            return f"Erreur validation: {exc.errors()}"
        except Exception as exc:  # noqa: BLE001
            return f"Erreur: {exc}"

    @app.callback(
        Output("v2m-save-choice", "style"),
        Input("v2m-save", "n_clicks"),
        Input("v2m-save-cancel", "n_clicks"),
        Input("v2m-save-local", "n_clicks"),
        Input("v2m-save-db", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_save_choice(_: int, __: int, ___: int, ____: int):
        if ctx.triggered_id == "v2m-save":
            return {"display": "block", "marginTop": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"}
        return {"display": "none", "marginTop": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"}

    @app.callback(
        Output("v2m-local-components", "data"),
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-pending-save", "data"),
        Output("v2m-update-modal", "opened"),
        Input("v2m-save-local", "n_clicks"),
        Input("v2m-save-db", "n_clicks"),
        State("v2m-model", "value"),
        State(ModelForm.ids.main(AIO_ID, FORM_ID), "data"),
        State("v2m-local-components", "data"),
        prevent_initial_call=True,
    )
    def save_component(_: int, __: int, model_key: str | None, form_data: dict[str, Any] | None, local_items: list[dict[str, Any]] | None):
        target = "db" if ctx.triggered_id == "v2m-save-db" else "local"
        if not model_key:
            return no_update, "Choisis un modele.", no_update, False
        if not isinstance(form_data, dict):
            return no_update, "Formulaire vide.", no_update, False

        try:
            raw = validate_form_data(model_key, form_data)
            name = str(raw.get("id", "")).strip()
            if not name:
                return no_update, "Nom requis.", no_update, False

            ctype, kind, payload = payload_from_data(model_key, raw)
            exists = any(str(it.get("name", "")) == name for it in (local_items or [])) if target == "local" else (get_template_by_name(name) is not None)
            pending = {
                "target": target,
                "name": name,
                "component_type": ctype,
                "kind": kind,
                "payload": payload,
                "raw": raw,
            }

            if exists:
                return no_update, f"Le nom '{name}' existe deja. Confirmation requise.", pending, True

            if target == "local":
                current = list(local_items or [])
                current.append({"name": name, "component_type": ctype, "kind": kind, "data": raw})
                return current, f"Composant local sauvegarde: {name}", {}, False

            upsert_template(name=name, family="General", component_type=ctype, kind=kind, payload=payload)
            return no_update, f"Composant sauvegarde en DB: {name}", {}, False
        except ValidationError as exc:
            return no_update, f"Erreur validation: {exc.errors()}", no_update, False
        except Exception as exc:  # noqa: BLE001
            return no_update, f"Erreur sauvegarde: {exc}", no_update, False

    @app.callback(
        Output("v2m-local-components", "data", allow_duplicate=True),
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-pending-save", "data", allow_duplicate=True),
        Output("v2m-update-modal", "opened", allow_duplicate=True),
        Input("v2m-update-yes", "n_clicks"),
        State("v2m-pending-save", "data"),
        State("v2m-local-components", "data"),
        prevent_initial_call=True,
    )
    def confirm_update(_: int, pending: dict[str, Any] | None, local_items: list[dict[str, Any]] | None):
        if not isinstance(pending, dict) or not pending:
            return no_update, "Aucune mise a jour en attente.", {}, False

        target = str(pending.get("target", ""))
        name = str(pending.get("name", ""))

        if target == "local":
            current = [it for it in list(local_items or []) if str(it.get("name", "")) != name]
            current.append(
                {
                    "name": name,
                    "component_type": str(pending.get("component_type", "")),
                    "kind": str(pending.get("kind", "")),
                    "data": pending.get("raw", {}),
                }
            )
            return current, f"Composant local mis a jour: {name}", {}, False

        upsert_template(
            name=name,
            family="General",
            component_type=str(pending.get("component_type", "")),
            kind=str(pending.get("kind", "")),
            payload=pending.get("payload", {}),
        )
        return no_update, f"Composant DB mis a jour: {name}", {}, False

    @app.callback(
        Output("v2m-update-modal", "opened", allow_duplicate=True),
        Input("v2m-update-no", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_update(_: int):
        return False

    @app.callback(
        Output("v2m-delete-modal", "opened"),
        Output("v2m-status", "children", allow_duplicate=True),
        Input("v2m-delete", "n_clicks"),
        State("v2m-select", "value"),
        prevent_initial_call=True,
    )
    def request_delete(_: int, selected_value: str | None):
        if not selected_value:
            return False, "Selectionne un composant a supprimer."
        return True, "Confirmation suppression ouverte."

    @app.callback(
        Output("v2m-local-components", "data", allow_duplicate=True),
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-delete-modal", "opened", allow_duplicate=True),
        Input("v2m-delete-yes", "n_clicks"),
        State("v2m-components-table", "data"),
        State("v2m-local-components", "data"),
        State("v2m-select", "value"),
        prevent_initial_call=True,
    )
    def confirm_delete(_: int, rows: list[dict[str, Any]] | None, local_items: list[dict[str, Any]] | None, selected_value: str | None):
        if not rows or not selected_value or "|" not in selected_value:
            return no_update, "Aucune selection a supprimer.", False

        scope, name = selected_value.split("|", 1)
        row = next((r for r in rows if str(r.get("_scope", "")) == scope and str(r.get("name", "")) == name), None)
        if row is None:
            return no_update, "Aucune selection a supprimer.", False

        if scope == "local":
            current = [it for it in list(local_items or []) if str(it.get("name", "")) != name]
            return current, f"Composant local supprime: {name}", False

        t = get_template_by_name(name)
        if t is None:
            return no_update, "Composant DB introuvable.", False
        delete_template(int(t["id"]))
        return no_update, f"Composant DB supprime: {name}", False

    @app.callback(
        Output("v2m-delete-modal", "opened", allow_duplicate=True),
        Input("v2m-delete-no", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_delete(_: int):
        return False
