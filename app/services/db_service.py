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

DB_PATH = Path(os.getenv("DB_PATH", "data/sismos.db"))


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


def _is_duplicate(conn, lat: float, lon: float, date: str, time: str,
                   magnitude: float = 0.0) -> bool:
    """Detecta duplicados entre agencias.
    Para M5+ usa ventana amplia (1.5° / 15 min) porque FUNVISIS puede reportar
    el epicentro en el centroide del estado, lejos de la ubicacion USGS/EMSC."""
    deg_tol = 1.5 if magnitude >= 5.0 else 0.2
    sec_tol = 900 if magnitude >= 5.0 else 300
    rows = conn.execute(
        "SELECT lat, lon, time FROM sismos WHERE date = ?", (date,)
    ).fetchall()
    try:
        t_new = datetime.strptime(time, "%H:%M")
    except ValueError:
        return False
    for row in rows:
        if abs(row["lat"] - lat) > deg_tol or abs(row["lon"] - lon) > deg_tol:
            continue
        try:
            t_existing = datetime.strptime(row["time"], "%H:%M")
            if abs((t_new - t_existing).total_seconds()) <= sec_tol:
                return True
        except ValueError:
            continue
    return False


def upsert_sismo(source: str, magnitude: float, lat: float, lon: float,
                 depth: str, place: str, date: str, time: str, country: str) -> bool:
    """Inserta un sismo si no existe. Retorna True si fue nuevo."""
    sid = _make_id(lat, lon, date, time)
    try:
        with get_conn() as conn:
            # Deduplicacion exacta por hash
            exists = conn.execute(
                "SELECT 1 FROM sismos WHERE id = ?", (sid,)
            ).fetchone()
            if exists:
                return False
            # Deduplicacion espaciotemporal (misma fuente puede tener coords ligeramente distintas)
            if _is_duplicate(conn, lat, lon, date, time, magnitude):
                return False
            conn.execute("""
                INSERT INTO sismos
                    (id, source, magnitude, lat, lon, depth, place, date, time, country)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (sid, source, magnitude, lat, lon, depth, place, date, time, country))
            conn.commit()
            return True
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


def dedup_existing() -> int:
    """Elimina duplicados ya guardados usando ventana espaciotemporal. Retorna cuantos se borraron."""
    eliminados = 0
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, lat, lon, date, time, magnitude FROM sismos ORDER BY first_seen ASC"
        ).fetchall()
        seen: list[dict] = []
        to_delete: list[str] = []
        for row in rows:
            mag = row["magnitude"] or 0.0
            deg_tol = 1.5 if mag >= 5.0 else 0.2
            sec_tol = 900 if mag >= 5.0 else 300
            is_dup = False
            try:
                t_new = datetime.strptime(row["time"], "%H:%M")
            except ValueError:
                seen.append(dict(row))
                continue
            for s in seen:
                if abs(s["lat"] - row["lat"]) > deg_tol or abs(s["lon"] - row["lon"]) > deg_tol:
                    continue
                if s["date"] != row["date"]:
                    continue
                try:
                    t_ex = datetime.strptime(s["time"], "%H:%M")
                    if abs((t_new - t_ex).total_seconds()) <= sec_tol:
                        is_dup = True
                        break
                except ValueError:
                    continue
            if is_dup:
                to_delete.append(row["id"])
            else:
                seen.append(dict(row))
        for sid in to_delete:
            conn.execute("DELETE FROM sismos WHERE id = ?", (sid,))
            eliminados += 1
        conn.commit()
    logger.info("dedup_existing: %d duplicados eliminados", eliminados)
    return eliminados
