"""
Persistance SQLite pour l'UI V2.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def _db_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "ui_v2.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    schema_sql = """
    CREATE TABLE IF NOT EXISTS component_templates_v2 (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      family TEXT NOT NULL,
      component_type TEXT NOT NULL,
      kind TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS brick_schemas_v2 (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      schema_json TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """
    with _connect() as conn:
        conn.executescript(schema_sql)
        conn.commit()


def list_templates() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, family, component_type, kind, payload_json, created_at, updated_at
            FROM component_templates_v2
            ORDER BY family ASC, name ASC
            """
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            payload = json.loads(str(r["payload_json"] or "{}"))
        except json.JSONDecodeError:
            payload = {}
        out.append(
            {
                "id": int(r["id"]),
                "name": str(r["name"]),
                "family": str(r["family"]),
                "component_type": str(r["component_type"]),
                "kind": str(r["kind"]),
                "payload": payload if isinstance(payload, dict) else {},
                "created_at": str(r["created_at"]),
                "updated_at": str(r["updated_at"]),
            }
        )
    return out


def get_template(template_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, family, component_type, kind, payload_json, created_at, updated_at
            FROM component_templates_v2
            WHERE id = ?
            """,
            (int(template_id),),
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(str(row["payload_json"] or "{}"))
    except json.JSONDecodeError:
        payload = {}
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "family": str(row["family"]),
        "component_type": str(row["component_type"]),
        "kind": str(row["kind"]),
        "payload": payload if isinstance(payload, dict) else {},
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def get_template_by_name(name: str) -> dict[str, Any] | None:
    raw_name = name.strip()
    if not raw_name:
        return None
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, family, component_type, kind, payload_json, created_at, updated_at
            FROM component_templates_v2
            WHERE name = ?
            """,
            (raw_name,),
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(str(row["payload_json"] or "{}"))
    except json.JSONDecodeError:
        payload = {}
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "family": str(row["family"]),
        "component_type": str(row["component_type"]),
        "kind": str(row["kind"]),
        "payload": payload if isinstance(payload, dict) else {},
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def upsert_template(
    *,
    name: str,
    family: str,
    component_type: str,
    kind: str,
    payload: dict[str, Any],
) -> int:
    raw_name = name.strip()
    raw_family = family.strip() or "General"
    raw_type = component_type.strip()
    raw_kind = kind.strip()
    if not raw_name:
        raise ValueError("Nom template obligatoire.")
    if not raw_type:
        raise ValueError("Type composant obligatoire.")
    if not isinstance(payload, dict):
        raise ValueError("Payload JSON doit etre un objet.")
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    update = """
    UPDATE component_templates_v2
    SET family = ?, component_type = ?, kind = ?, payload_json = ?, updated_at = datetime('now')
    WHERE name = ?
    """
    insert = """
    INSERT INTO component_templates_v2(name, family, component_type, kind, payload_json)
    VALUES(?, ?, ?, ?, ?)
    """
    with _connect() as conn:
        cur = conn.execute(update, (raw_family, raw_type, raw_kind, payload_json, raw_name))
        if cur.rowcount == 0:
            cur = conn.execute(insert, (raw_name, raw_family, raw_type, raw_kind, payload_json))
            template_id = int(cur.lastrowid)
        else:
            row = conn.execute("SELECT id FROM component_templates_v2 WHERE name = ?", (raw_name,)).fetchone()
            if row is None:
                raise RuntimeError("Template introuvable apres update.")
            template_id = int(row["id"])
        conn.commit()
        return template_id


def delete_template(template_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM component_templates_v2 WHERE id = ?", (int(template_id),))
        conn.commit()


def list_schemas() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, schema_json, created_at, updated_at
            FROM brick_schemas_v2
            ORDER BY name ASC
            """
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            schema = json.loads(str(r["schema_json"] or "{}"))
        except json.JSONDecodeError:
            schema = {}
        out.append(
            {
                "id": int(r["id"]),
                "name": str(r["name"]),
                "schema": schema if isinstance(schema, dict) else {},
                "created_at": str(r["created_at"]),
                "updated_at": str(r["updated_at"]),
            }
        )
    return out


def get_schema(schema_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, schema_json, created_at, updated_at
            FROM brick_schemas_v2
            WHERE id = ?
            """,
            (int(schema_id),),
        ).fetchone()
    if row is None:
        return None
    try:
        schema = json.loads(str(row["schema_json"] or "{}"))
    except json.JSONDecodeError:
        schema = {}
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "schema": schema if isinstance(schema, dict) else {},
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def upsert_schema(name: str, schema: dict[str, Any]) -> int:
    raw_name = name.strip()
    if not raw_name:
        raise ValueError("Nom schema obligatoire.")
    if not isinstance(schema, dict):
        raise ValueError("Schema invalide.")
    schema_json = json.dumps(schema, ensure_ascii=False, sort_keys=True)
    update = """
    UPDATE brick_schemas_v2
    SET schema_json = ?, updated_at = datetime('now')
    WHERE name = ?
    """
    insert = """
    INSERT INTO brick_schemas_v2(name, schema_json)
    VALUES(?, ?)
    """
    with _connect() as conn:
        cur = conn.execute(update, (schema_json, raw_name))
        if cur.rowcount == 0:
            cur = conn.execute(insert, (raw_name, schema_json))
            schema_id = int(cur.lastrowid)
        else:
            row = conn.execute("SELECT id FROM brick_schemas_v2 WHERE name = ?", (raw_name,)).fetchone()
            if row is None:
                raise RuntimeError("Schema introuvable apres update.")
            schema_id = int(row["id"])
        conn.commit()
        return schema_id
