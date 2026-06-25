"""
Endpoint para el registro historico propio de sismos
"""
from fastapi import APIRouter, Query
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
