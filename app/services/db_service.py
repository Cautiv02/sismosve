"""
Servicio de base de datos SQLite para registro historico de sismos
"""

import os
import sqlite3
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("/tmp/sismos.db")


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sismos (
                id          TEXT PRIMARY KEY,
                source      TEXT NOT NULL,
                magnitude   REAL,
                lat         REAL,
                lon         REAL,
                depth       TEXT,
                place       TEXT,
                date        TEXT,
                time        TEXT,
                country     TEXT,
                first_seen  TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON sismos(date, time)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mag  ON sismos(magnitude)")
        conn.commit()
    logger.info("DB inicializada en %s", DB_PATH)


def _make_id(lat: float, lon: float, date: str, time: str) -> str:
    key = f"{round(lat,2)}|{round(lon,2)}|{date}|{time}"
    return hashlib.md5(key.encode()).hexdigest()


def upsert_sismo(source: str, magnitude: float, lat: float, lon: float,
                 depth: str, place: str, date: str, time: str, country: str) -> bool:
    """Inserta un sismo si no existe. Retorna True si fue nuevo."""
    sid = _make_id(lat, lon, date, time)
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO sismos
                    (id, source, magnitude, lat, lon, depth, place, date, time, country)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (sid, source, magnitude, lat, lon, depth, place, date, time, country))
            conn.commit()
            return conn.execute("SELECT changes()").fetchone()[0] > 0
    except Exception as e:
        logger.error("Error upsert sismo: %s", e)
        return False


def get_sismos(limit: int = 500, offset: int = 0) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM sismos
            ORDER BY date DESC, time DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
    return [dict(r) for r in rows]


def get_total() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM sismos").fetchone()[0]
