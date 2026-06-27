"""
Servicio de base de datos - SQLite (local) o PostgreSQL (production via DATABASE_URL)
"""

import os
import hashlib
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DATABASE_URL = os.getenv("DATABASE_URL", "")
_DB_PATH = Path(os.getenv("DB_PATH", "data/sismos.db"))
USE_PG = bool(_DATABASE_URL)
PH = "%s" if USE_PG else "?"


def _get_conn():
    if USE_PG:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(_DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = False
        return conn
    else:
        import sqlite3
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if USE_PG:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sismos (
                    id         TEXT PRIMARY KEY,
                    source     TEXT NOT NULL,
                    magnitude  REAL,
                    lat        REAL,
                    lon        REAL,
                    depth      TEXT,
                    place      TEXT,
                    date       TEXT,
                    time       TEXT,
                    country    TEXT,
                    first_seen TEXT DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
                )
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sismos (
                    id         TEXT PRIMARY KEY,
                    source     TEXT NOT NULL,
                    magnitude  REAL,
                    lat        REAL,
                    lon        REAL,
                    depth      TEXT,
                    place      TEXT,
                    date       TEXT,
                    time       TEXT,
                    country    TEXT,
                    first_seen TEXT DEFAULT (datetime('now'))
                )
            """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_date ON sismos(date, time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mag  ON sismos(magnitude)")
        conn.commit()
    finally:
        conn.close()
    logger.info("DB (%s) inicializada", "PostgreSQL" if USE_PG else f"SQLite @ {_DB_PATH}")


def _make_id(lat: float, lon: float, date: str, time: str) -> str:
    key = f"{round(lat,2)}|{round(lon,2)}|{date}|{time}"
    return hashlib.md5(key.encode()).hexdigest()


def _is_duplicate(cur, lat: float, lon: float, date: str, time: str, magnitude: float = 0.0) -> bool:
    """Detecta duplicados entre agencias. M7+ nunca se deduplica — son eventos raros y siempre distintos."""
    if magnitude >= 7.0:
        return False
    deg_tol = 1.5 if magnitude >= 5.0 else 0.2
    sec_tol = 900 if magnitude >= 5.0 else 300
    mag_tol = 0.5  # diferencia maxima para considerar mismo evento
    cur.execute(f"SELECT lat, lon, time, magnitude FROM sismos WHERE date = {PH}", (date,))
    rows = cur.fetchall()
    try:
        t_new = datetime.strptime(time, "%H:%M")
    except ValueError:
        return False
    for row in rows:
        r = dict(row)
        # Si las magnitudes difieren mas de 0.5, son eventos distintos
        if abs((r.get("magnitude") or 0) - magnitude) > mag_tol:
            continue
        if abs(r["lat"] - lat) > deg_tol or abs(r["lon"] - lon) > deg_tol:
            continue
        try:
            if abs((t_new - datetime.strptime(r["time"], "%H:%M")).total_seconds()) <= sec_tol:
                return True
        except ValueError:
            continue
    return False


def upsert_sismo(source: str, magnitude: float, lat: float, lon: float,
                 depth: str, place: str, date: str, time: str, country: str) -> bool:
    """Inserta un sismo si no existe. Retorna True si fue nuevo."""
    sid = _make_id(lat, lon, date, time)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM sismos WHERE id = {PH}", (sid,))
        if cur.fetchone():
            return False
        if _is_duplicate(cur, lat, lon, date, time, magnitude):
            return False
        if USE_PG:
            cur.execute(f"""
                INSERT INTO sismos (id, source, magnitude, lat, lon, depth, place, date, time, country)
                VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})
                ON CONFLICT (id) DO NOTHING
            """, (sid, source, magnitude, lat, lon, depth, place, date, time, country))
        else:
            cur.execute(f"""
                INSERT OR IGNORE INTO sismos
                    (id, source, magnitude, lat, lon, depth, place, date, time, country)
                VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})
            """, (sid, source, magnitude, lat, lon, depth, place, date, time, country))
        conn.commit()
        return (cur.rowcount or 0) > 0
    except Exception as e:
        logger.error("Error upsert: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()


def get_sismos(limit: int = 500, offset: int = 0) -> list[dict]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM sismos ORDER BY date DESC, time DESC LIMIT {PH} OFFSET {PH}",
            (limit, offset)
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_total() -> int:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM sismos")
        row = dict(cur.fetchone())
        return row.get("cnt", 0)
    finally:
        conn.close()


def delete_by_place(place_pattern: str) -> int:
    """Elimina eventos cuyo campo place contenga el patron dado (case-insensitive)."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if USE_PG:
            cur.execute("DELETE FROM sismos WHERE UPPER(place) LIKE UPPER(%s)", (f"%{place_pattern}%",))
        else:
            cur.execute("DELETE FROM sismos WHERE UPPER(place) LIKE UPPER(?)", (f"%{place_pattern}%",))
        conn.commit()
        return cur.rowcount or 0
    except Exception as e:
        logger.error("Error delete_by_place: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        conn.close()


def dedup_existing() -> int:
    """Elimina duplicados ya guardados. Retorna cuántos se borraron."""
    eliminados = 0
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, lat, lon, date, time, magnitude FROM sismos ORDER BY first_seen ASC")
        rows = [dict(r) for r in cur.fetchall()]
        seen: list[dict] = []
        to_delete: list[str] = []
        for row in rows:
            mag = row.get("magnitude") or 0.0
            if mag >= 7.0:
                seen.append(row)
                continue
            deg_tol = 1.5 if mag >= 5.0 else 0.2
            sec_tol = 900 if mag >= 5.0 else 300
            is_dup = False
            try:
                t_new = datetime.strptime(row["time"], "%H:%M")
            except ValueError:
                seen.append(row)
                continue
            for s in seen:
                if s["date"] != row["date"]:
                    continue
                if abs((s.get("magnitude") or 0) - mag) > 0.5:
                    continue
                if abs(s["lat"] - row["lat"]) > deg_tol or abs(s["lon"] - row["lon"]) > deg_tol:
                    continue
                try:
                    if abs((t_new - datetime.strptime(s["time"], "%H:%M")).total_seconds()) <= sec_tol:
                        is_dup = True
                        break
                except ValueError:
                    continue
            if is_dup:
                to_delete.append(row["id"])
            else:
                seen.append(row)
        for sid in to_delete:
            cur.execute(f"DELETE FROM sismos WHERE id = {PH}", (sid,))
            eliminados += 1
        conn.commit()
    finally:
        conn.close()
    logger.info("dedup_existing: %d eliminados", eliminados)
    return eliminados
