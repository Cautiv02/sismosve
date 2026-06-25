"""
Router para datos de sismos globales desde USGS
"""

import logging
from datetime import datetime, timezone, timedelta

VET = timezone(timedelta(hours=-4))
import aiohttp
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["USGS"])

USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
USGS_PARAMS = {
    "format": "geojson",
    "limit": 150,
    "orderby": "time",
    "minmagnitude": "1.5",
}


def _transform_feature(feature: dict) -> dict:
    props = feature.get("properties", {})
    coords = feature.get("geometry", {}).get("coordinates", [0, 0, 0])

    ts_ms = props.get("time") or 0
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=VET)
        date_str = dt.strftime("%d-%m-%Y")
        time_str = dt.strftime("%H:%M")
    except Exception:
        date_str = "-"
        time_str = "-"

    mag = props.get("mag") or 0
    depth = coords[2] if len(coords) > 2 else 0
    lat = coords[1] if len(coords) > 1 else 0
    lng = coords[0] if len(coords) > 0 else 0

    return {
        "type": "Sismo",
        "geometry": {"type": "Point", "coordinates": coords},
        "properties": {
            "value": f"{float(mag):.1f}",
            "addressFormatted": props.get("place") or "Ubicacion desconocida",
            "date": date_str,
            "time": time_str,
            "depth": f"{float(depth):.1f} km",
            "lat": str(round(float(lat), 4)),
            "long": str(round(float(lng), 4)),
            "country": "Global",
        },
    }


@router.get("/usgs")
async def get_usgs_sismos():
    """Obtiene sismos recientes desde la API publica de USGS"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(USGS_URL, params=USGS_PARAMS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=502, detail="Error al obtener datos de USGS")
                raw = await resp.json()

        features = [_transform_feature(f) for f in raw.get("features", [])]
        return {"type": "FeatureCollection", "features": features}

    except aiohttp.ClientError as e:
        logger.error("Error de conexion USGS: %s", e)
        raise HTTPException(status_code=502, detail="No se pudo conectar con USGS")
    except Exception as e:
        logger.error("Error USGS: %s", e)
        raise HTTPException(status_code=500, detail="Error interno")
