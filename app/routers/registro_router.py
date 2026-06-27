"""
Endpoint para el registro historico propio de sismos
"""
import os
from fastapi import APIRouter, Query, HTTPException
from ..services import db_service

router = APIRouter(prefix="/api", tags=["Registro"])


def _to_feature(row: dict) -> dict:
    return {
        "type": "Sismo",
        "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
        "properties": {
            "value":            str(round(row["magnitude"], 1)),
            "addressFormatted": row["place"],
            "date":             row["date"],
            "time":             row["time"],
            "depth":            row["depth"],
            "lat":              str(row["lat"]),
            "long":             str(row["lon"]),
            "country":          row["country"],
            "source":           row["source"],
        },
    }


@router.post("/registro/import")
async def import_registro(payload: dict, key: str = Query(...)):
    """Importa eventos al registro. Requiere clave secreta."""
    secret = os.getenv("IMPORT_KEY", "")
    if not secret or key != secret:
        raise HTTPException(status_code=403, detail="Clave invalida")
    features = payload.get("features", [])
    nuevos = 0
    for f in features:
        p = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [0, 0, 0])
        try:
            if db_service.upsert_sismo(
                source=p.get("source", "LOCAL"),
                magnitude=float(p.get("value", 0)),
                lat=float(p.get("lat", coords[1])),
                lon=float(p.get("long", coords[0])),
                depth=p.get("depth", "0 km"),
                place=p.get("addressFormatted", ""),
                date=p.get("date", ""),
                time=p.get("time", ""),
                country=p.get("country", "Venezuela"),
            ):
                nuevos += 1
        except Exception:
            continue
    return {"imported": nuevos, "total": db_service.get_total()}


@router.delete("/registro/delete")
async def delete_by_place(place: str = Query(...), key: str = Query(...)):
    """Elimina eventos cuyo lugar contenga el texto dado. Requiere clave secreta."""
    secret = os.getenv("IMPORT_KEY", "")
    if not secret or key != secret:
        raise HTTPException(status_code=403, detail="Clave invalida")
    eliminados = db_service.delete_by_place(place)
    return {"eliminados": eliminados, "total": db_service.get_total()}


@router.post("/registro/dedup")
async def dedup_registro(key: str = Query(...)):
    """Elimina duplicados existentes en la DB usando ventana espaciotemporal."""
    secret = os.getenv("IMPORT_KEY", "")
    if not secret or key != secret:
        raise HTTPException(status_code=403, detail="Clave invalida")
    eliminados = db_service.dedup_existing()
    return {"eliminados": eliminados, "total": db_service.get_total()}


@router.get("/registro")
async def get_registro(
    limit:  int = Query(default=500, ge=1,  le=2000),
    offset: int = Query(default=0,   ge=0),
):
    """Registro historico propio combinando FUNVISIS + USGS Venezuela"""
    rows = db_service.get_sismos(limit=limit, offset=offset)
    total = db_service.get_total()
    return {
        "type": "FeatureCollection",
        "features": [_to_feature(r) for r in rows],
        "meta": {"total": total, "returned": len(rows), "offset": offset},
    }
