"""Callbacks UI V2 composants (DB-only)."""

from __future__ import annotations

from typing import Any

from dash import Input, Output, State, ctx, no_update
from dash_pydantic_form import ModelForm
from pydantic import ValidationError

from components_basemodel import COURSES_NUMBER
from components_registry import (
    AIO_ID,
    FORM_ID,
    db_config_rows,
    db_rows,
    default_model_key,
    model_options,
    payload_from_data,
    render_form,
    seed_from_template,
    validate_form_data,
)
from services.storage import delete_template, get_template_by_name, list_schemas, upsert_schema, upsert_template


PLACEHOLDER_MERMAID = 'flowchart LR\n  n0["Visualisation DAG en cours de finalisation"]\n  n1["Placeholder"]\n  n0 --> n1'


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
        Input("v2cfg-save-db", "n_clicks"),
        prevent_initial_call=True,
    )
    def cfg_toggle_save_choice(_: int, __: int, ___: int):
        if ctx.triggered_id == "v2cfg-save":
            return {"display": "block", "marginBottom": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"}
        return {"display": "none", "marginBottom": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"}

    @app.callback(
        Output("v2cfg-add-component", "options"),
        Output("v2cfg-remove-component", "options"),
        Output("v2cfg-select", "options"),
        Output("v2cfg-table", "data"),
        Output("v2cfg-mermaid", "chart"),
        Input("v2m-refresh", "n_intervals"),
        Input("v2cfg-current", "data"),
        Input("v2cfg-save-db", "n_clicks"),
        Input("v2m-save-db", "n_clicks"),
        Input("v2m-update-yes", "n_clicks"),
        Input("v2m-delete-yes", "n_clicks"),
    )
    def cfg_refresh(_: int, current_cfg: dict[str, Any] | None, __: int, ___: int, ____: int, _____: int):
        current = current_cfg if isinstance(current_cfg, dict) else {"name": "config_local", "components": []}
        comps = current.get("components", [])

        db_components = db_rows()
        add_opts = [{"label": str(c.get("name", "")), "value": str(c.get("name", ""))} for c in db_components if str(c.get("name", "")).strip()]
        rem_opts = [{"label": str(c.get("name", "")), "value": str(c.get("name", ""))} for c in comps if isinstance(c, dict) and str(c.get("name", "")).strip()]

        cfg_rows = db_config_rows()
        cfg_opts = [{"label": str(r.get("name", "")), "value": str(r.get("name", ""))} for r in cfg_rows if str(r.get("name", "")).strip()]

        return add_opts, rem_opts, cfg_opts, cfg_rows, PLACEHOLDER_MERMAID

    @app.callback(
        Output("v2cfg-current", "data"),
        Output("v2cfg-status", "children"),
        Input("v2cfg-add-btn", "n_clicks"),
        State("v2cfg-add-component", "value"),
        State("v2cfg-current", "data"),
        prevent_initial_call=True,
    )
    def cfg_add_component(_: int, comp_name: str | None, current_cfg: dict[str, Any] | None):
        if not comp_name:
            return no_update, "Selectionne un composant a ajouter."

        tmpl = get_template_by_name(str(comp_name))
        if tmpl is None:
            return no_update, "Composant DB introuvable."

        ctype = str(tmpl.get("component_type", ""))
        kind = str(tmpl.get("kind", ""))
        model_key, seed = seed_from_template(ctype, kind, tmpl.get("payload", {}))
        if model_key is None:
            return no_update, "Template incompatible avec le formulaire actif."

        current = current_cfg if isinstance(current_cfg, dict) else {"name": "config_local", "components": []}
        comps = [c for c in current.get("components", []) if isinstance(c, dict)]
        if any(str(c.get("name", "")) == str(comp_name) for c in comps):
            return no_update, f"Le composant '{comp_name}' est deja dans la config."

        comps.append(
            {
                "name": str(comp_name),
                "component_type": ctype,
                "kind": kind,
                "data": seed if isinstance(seed, dict) else {},
            }
        )
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
        Output("v2cfg-status", "children", allow_duplicate=True),
        Input("v2cfg-load", "n_clicks"),
        State("v2cfg-select", "value"),
        prevent_initial_call=True,
    )
    def cfg_load(_: int, selected: str | None):
        if not selected:
            return no_update, "Selectionne une configuration."
        row = next((r for r in list_schemas() if str(r.get("name", "")) == str(selected)), None)
        cfg = row.get("schema", {}) if isinstance(row, dict) else None
        if not isinstance(cfg, dict):
            return no_update, "Configuration introuvable."
        return cfg, f"Configuration chargee: {selected}"

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
        Input("v2m-refresh", "n_intervals"),
        Input("v2m-save-db", "n_clicks"),
        Input("v2m-update-yes", "n_clicks"),
        Input("v2m-delete-yes", "n_clicks"),
    )
    def selector_options(_: int, __: int, ___: int, ____: int):
        return [{"label": str(r.get("name", "")), "value": str(r.get("name", ""))} for r in db_rows() if str(r.get("name", "")).strip()]

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
        Output("v2m-form-seed", "data", allow_duplicate=True),
        Input(ModelForm.ids.main(AIO_ID, FORM_ID), "data"),
        State("v2m-model", "value"),
        State("v2m-form-seed", "data"),
        prevent_initial_call=True,
    )
    def nav_course_filter_seed(
        form_data: dict[str, Any] | None,
        model_key: str | None,
        current_seed: dict[str, Any] | None,
    ):
        if model_key != "profile.nav_speed":
            return no_update
        if not isinstance(form_data, dict):
            return no_update

        cruise_name = str(form_data.get("cruise_name", ""))
        select_mode = str(form_data.get("select", "cruise"))

        prev = current_seed if isinstance(current_seed, dict) else {}
        if cruise_name == str(prev.get("cruise_name", "")) and select_mode == str(prev.get("select", "cruise")):
            return no_update

        seed = dict(form_data)
        if select_mode != "course":
            seed["course_no"] = None
            return seed

        allowed = {str(n) for n in COURSES_NUMBER.get(cruise_name, [])}
        course_no = seed.get("course_no")
        if course_no is not None and str(course_no) not in allowed:
            seed["course_no"] = None
        return seed

    @app.callback(
        Output("v2m-type", "value", allow_duplicate=True),
        Output("v2m-model", "value", allow_duplicate=True),
        Output("v2m-form-seed", "data", allow_duplicate=True),
        Output("v2m-status", "children", allow_duplicate=True),
        Input("v2m-load-edit", "n_clicks"),
        State("v2m-select", "value"),
        prevent_initial_call=True,
    )
    def load_edit(_: int, selected_name: str | None):
        if not selected_name:
            return no_update, no_update, no_update, "Selectionne un composant a editer."

        t = get_template_by_name(selected_name)
        if t is None:
            return no_update, no_update, no_update, "Composant DB introuvable."

        ctype = str(t.get("component_type", ""))
        kind = str(t.get("kind", ""))
        model_key, seed = seed_from_template(ctype, kind, t.get("payload", {}))
        if model_key is None:
            return no_update, no_update, no_update, "Type/Kind non supporte par ce formulaire."

        return ctype, model_key, seed, f"Edition chargee: {selected_name}"

    @app.callback(
        Output("v2m-status", "children"),
        Input("v2m-validate", "n_clicks"),
        State("v2m-model", "value"),
        State(ModelForm.ids.main(AIO_ID, FORM_ID), "data"),
        prevent_initial_call=True,
    )
    def validate(_: int, model_key: str | None, form_data: dict[str, Any] | None):
        if not model_key:
            return "Choisis un modele."
        if not isinstance(form_data, dict):
            return "Formulaire vide."
        try:
            raw = validate_form_data(model_key, form_data)
            name = str(raw.get("id", "")).strip()
            if not name:
                return "Erreur validation: nom requis."
            if get_template_by_name(name) is not None:
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
        Input("v2m-save-db", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_save_choice(_: int, __: int, ___: int):
        if ctx.triggered_id == "v2m-save":
            return {"display": "block", "marginTop": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"}
        return {"display": "none", "marginTop": "8px", "padding": "8px", "border": "1px solid #ddd", "borderRadius": "8px"}

    @app.callback(
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-pending-save", "data"),
        Output("v2m-update-modal", "opened"),
        Input("v2m-save-db", "n_clicks"),
        State("v2m-model", "value"),
        State(ModelForm.ids.main(AIO_ID, FORM_ID), "data"),
        prevent_initial_call=True,
    )
    def save_component(_: int, model_key: str | None, form_data: dict[str, Any] | None):
        if not model_key:
            return "Choisis un modele.", no_update, False
        if not isinstance(form_data, dict):
            return "Formulaire vide.", no_update, False

        try:
            raw = validate_form_data(model_key, form_data)
            name = str(raw.get("id", "")).strip()
            if not name:
                return "Nom requis.", no_update, False

            ctype, kind, payload = payload_from_data(model_key, raw)
            exists = get_template_by_name(name) is not None
            pending = {
                "name": name,
                "component_type": ctype,
                "kind": kind,
                "payload": payload,
            }

            if exists:
                return f"Le nom '{name}' existe deja. Confirmation requise.", pending, True

            upsert_template(name=name, family="General", component_type=ctype, kind=kind, payload=payload)
            return f"Composant sauvegarde en DB: {name}", {}, False
        except ValidationError as exc:
            return f"Erreur validation: {exc.errors()}", no_update, False
        except Exception as exc:  # noqa: BLE001
            return f"Erreur sauvegarde: {exc}", no_update, False

    @app.callback(
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-pending-save", "data", allow_duplicate=True),
        Output("v2m-update-modal", "opened", allow_duplicate=True),
        Input("v2m-update-yes", "n_clicks"),
        State("v2m-pending-save", "data"),
        prevent_initial_call=True,
    )
    def confirm_update(_: int, pending: dict[str, Any] | None):
        if not isinstance(pending, dict) or not pending:
            return "Aucune mise a jour en attente.", {}, False

        upsert_template(
            name=str(pending.get("name", "")),
            family="General",
            component_type=str(pending.get("component_type", "")),
            kind=str(pending.get("kind", "")),
            payload=pending.get("payload", {}),
        )
        return f"Composant DB mis a jour: {str(pending.get('name', ''))}", {}, False

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
        Output("v2m-status", "children", allow_duplicate=True),
        Output("v2m-delete-modal", "opened", allow_duplicate=True),
        Input("v2m-delete-yes", "n_clicks"),
        State("v2m-select", "value"),
        prevent_initial_call=True,
    )
    def confirm_delete(_: int, selected_value: str | None):
        if not selected_value:
            return "Aucune selection a supprimer.", False

        t = get_template_by_name(selected_value)
        if t is None:
            return "Composant DB introuvable.", False
        delete_template(int(t["id"]))
        return f"Composant DB supprime: {selected_value}", False

    @app.callback(
        Output("v2m-delete-modal", "opened", allow_duplicate=True),
        Input("v2m-delete-no", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_delete(_: int):
        return False
