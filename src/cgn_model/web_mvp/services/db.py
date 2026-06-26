"""
Couche SQLite minimale pour le MVP web.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from cgn_model.web_common.local_db import local_db


@dataclass(frozen=True)
class VesselConfigRow:
    """
    Enregistrement de configuration vessel.
    """

    id: int
    name: str
    yaml_text: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ComponentTemplateRow:
    """
    Enregistrement de template composant.
    """

    id: int
    name: str
    component_type: str
    kind: str
    payload: dict
    created_at: str
    updated_at: str


_LOCAL_DB = local_db(
    package="cgn_model.web_mvp",
    template_name="mvp_template.db",
    db_name="mvp.db",
)


def _db_path() -> Path:
    return _LOCAL_DB.path




def db_path() -> Path:
    """Retourne le chemin de la base SQLite utilisateur du MVP."""

    return _db_path()


def connect_db() -> sqlite3.Connection:
    """
    Ouvre une connexion SQLite.
    """
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn



def _schema_sql() -> str:
    return """
    CREATE TABLE IF NOT EXISTS vessel_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        yaml_text TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS component_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        component_type TEXT NOT NULL,
        kind TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """


def init_db() -> Path:
    """
    Initialise le schema de base.
    """
    sql = _schema_sql()
    with connect_db() as conn:
        conn.executescript(sql)
        conn.commit()
    return _db_path()


def list_vessel_configs() -> list[VesselConfigRow]:
    """
    Retourne toutes les configurations, triees par nom.
    """
    query = """
    SELECT id, name, yaml_text, created_at, updated_at
    FROM vessel_configs
    ORDER BY name ASC
    """
    with connect_db() as conn:
        rows = conn.execute(query).fetchall()
    return [
        VesselConfigRow(
            id=int(r["id"]),
            name=str(r["name"]),
            yaml_text=str(r["yaml_text"]),
            created_at=str(r["created_at"]),
            updated_at=str(r["updated_at"]),
        )
        for r in rows
    ]


def upsert_vessel_config(name: str, yaml_text: str) -> int:
    """
    Cree ou met a jour une configuration par nom.
    """
    if not name.strip():
        raise ValueError("Le nom ne peut pas etre vide.")
    if not yaml_text.strip():
        raise ValueError("Le YAML ne peut pas etre vide.")

    update = """
    UPDATE vessel_configs
    SET yaml_text = ?, updated_at = datetime('now')
    WHERE name = ?
    """
    insert = """
    INSERT INTO vessel_configs(name, yaml_text)
    VALUES(?, ?)
    """
    select_id = "SELECT id FROM vessel_configs WHERE name = ?"
    with connect_db() as conn:
        cur = conn.execute(update, (yaml_text, name.strip()))
        if cur.rowcount == 0:
            cur = conn.execute(insert, (name.strip(), yaml_text))
            config_id = int(cur.lastrowid)
        else:
            row = conn.execute(select_id, (name.strip(),)).fetchone()
            if row is None:
                raise RuntimeError("Configuration introuvable apres update.")
            config_id = int(row["id"])
        conn.commit()
        return config_id


def delete_vessel_config(config_id: int) -> None:
    """
    Supprime une configuration par id.
    """
    with connect_db() as conn:
        conn.execute("DELETE FROM vessel_configs WHERE id = ?", (int(config_id),))
        conn.commit()


def get_vessel_config(config_id: int) -> VesselConfigRow | None:
    """
    Retourne une configuration par id.
    """
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT id, name, yaml_text, created_at, updated_at
            FROM vessel_configs
            WHERE id = ?
            """,
            (int(config_id),),
        ).fetchone()
    if row is None:
        return None
    return VesselConfigRow(
        id=int(row["id"]),
        name=str(row["name"]),
        yaml_text=str(row["yaml_text"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def get_vessel_config_by_name(name: str) -> VesselConfigRow | None:
    """
    Retourne une configuration par nom (exact, insensible aux espaces de bord).
    """
    normalized = name.strip()
    if not normalized:
        return None
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT id, name, yaml_text, created_at, updated_at
            FROM vessel_configs
            WHERE name = ?
            """,
            (normalized,),
        ).fetchone()
    if row is None:
        return None
    return VesselConfigRow(
        id=int(row["id"]),
        name=str(row["name"]),
        yaml_text=str(row["yaml_text"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def list_component_templates(component_type: str | None = None) -> list[ComponentTemplateRow]:
    """
    Retourne les templates composants, filtres optionnellement par type.
    """
    base_query = """
    SELECT id, name, component_type, kind, payload_json, created_at, updated_at
    FROM component_templates
    """
    params: tuple = ()
    if component_type:
        query = base_query + " WHERE component_type = ? ORDER BY name ASC"
        params = (component_type.strip(),)
    else:
        query = base_query + " ORDER BY component_type ASC, name ASC"

    with connect_db() as conn:
        rows = conn.execute(query, params).fetchall()

    out: list[ComponentTemplateRow] = []
    for r in rows:
        payload_raw = str(r["payload_json"] or "{}")
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        out.append(
            ComponentTemplateRow(
                id=int(r["id"]),
                name=str(r["name"]),
                component_type=str(r["component_type"]),
                kind=str(r["kind"]),
                payload=payload,
                created_at=str(r["created_at"]),
                updated_at=str(r["updated_at"]),
            )
        )
    return out


def get_component_template(template_id: int) -> ComponentTemplateRow | None:
    """
    Retourne un template composant par id.
    """
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT id, name, component_type, kind, payload_json, created_at, updated_at
            FROM component_templates
            WHERE id = ?
            """,
            (int(template_id),),
        ).fetchone()
    if row is None:
        return None
    payload_raw = str(row["payload_json"] or "{}")
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return ComponentTemplateRow(
        id=int(row["id"]),
        name=str(row["name"]),
        component_type=str(row["component_type"]),
        kind=str(row["kind"]),
        payload=payload,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def get_component_template_by_name(name: str) -> ComponentTemplateRow | None:
    """
    Retourne un template composant par nom.
    """
    normalized = name.strip()
    if not normalized:
        return None
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT id, name, component_type, kind, payload_json, created_at, updated_at
            FROM component_templates
            WHERE name = ?
            """,
            (normalized,),
        ).fetchone()
    if row is None:
        return None
    payload_raw = str(row["payload_json"] or "{}")
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return ComponentTemplateRow(
        id=int(row["id"]),
        name=str(row["name"]),
        component_type=str(row["component_type"]),
        kind=str(row["kind"]),
        payload=payload,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def upsert_component_template(
    name: str,
    component_type: str,
    payload: dict,
) -> int:
    """
    Cree ou met a jour un template composant par nom.
    """
    raw_name = name.strip()
    raw_type = component_type.strip()
    if not raw_name:
        raise ValueError("Le nom du template ne peut pas etre vide.")
    if raw_type not in {"profile", "adapter", "input", "converter", "storage"}:
        raise ValueError(f"Type composant invalide: {raw_type!r}")
    if not isinstance(payload, dict):
        raise ValueError("Le payload doit etre un objet JSON (dict).")

    component = payload.get("component", payload)
    if not isinstance(component, dict):
        component = {}
    raw_kind = str(component.get("kind", "")).strip()
    if raw_type in {"profile", "adapter", "converter"} and not raw_kind:
        raise ValueError(f"Le kind est requis dans payload.component.kind pour type={raw_type!r}.")
    # Pour input/storage, kind peut rester vide.

    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    update = """
    UPDATE component_templates
    SET component_type = ?, kind = ?, payload_json = ?, updated_at = datetime('now')
    WHERE name = ?
    """
    insert = """
    INSERT INTO component_templates(name, component_type, kind, payload_json)
    VALUES(?, ?, ?, ?)
    """
    select_id = "SELECT id FROM component_templates WHERE name = ?"
    with connect_db() as conn:
        cur = conn.execute(update, (raw_type, raw_kind, payload_json, raw_name))
        if cur.rowcount == 0:
            cur = conn.execute(insert, (raw_name, raw_type, raw_kind, payload_json))
            template_id = int(cur.lastrowid)
        else:
            row = conn.execute(select_id, (raw_name,)).fetchone()
            if row is None:
                raise RuntimeError("Template introuvable apres update.")
            template_id = int(row["id"])
        conn.commit()
        return template_id


def delete_component_template(template_id: int) -> None:
    """
    Supprime un template composant par id.
    """
    with connect_db() as conn:
        conn.execute("DELETE FROM component_templates WHERE id = ?", (int(template_id),))
        conn.commit()


