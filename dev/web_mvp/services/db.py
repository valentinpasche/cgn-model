"""
Couche SQLite minimale pour le MVP web.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


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


def _db_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "mvp.db"


def connect_db() -> sqlite3.Connection:
    """
    Ouvre une connexion SQLite.
    """
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Initialise le schema de base.
    """
    sql = """
    CREATE TABLE IF NOT EXISTS vessel_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        yaml_text TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """
    with connect_db() as conn:
        conn.execute(sql)
        conn.commit()


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
