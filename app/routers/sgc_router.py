"""
Router para datos de sismos desde SGC Colombia (Servicio Geologico Colombiano)
Filtrables por region de Venezuela
"""

import logging
from datetime import datetime, timedelta
import aiohttp
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["SGC"])

SGC_API = "https://apicatalogador.sgc.gov.co/api/events/search/"
SGC_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.sgc.gov.co/sismos",
    "Origin": "https://www.sgc.gov.co",
    "Content-Type": "application/json",
}

# Bounding box Venezuela + borde colombiano cercano (ampliado al norte para capturar costa Caribe)
VE_LAT_MIN = 0.6
VE_LAT_MAX = 15.0
VE_LON_MIN = -73.5
VE_LON_MAX = -59.8


def _transform(item: dict) -> dict:
    try:
        local_time = item.get("local_time") or ""
        if local_time:
            dt = datetime.strptime(local_time, "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%d-%m-%Y")
            time_str = dt.strftime("%H:%M")
        else:
            date_str = "-"
            time_str = "-"
    except Exception:
        date_str = "-"
        time_str = "-"

    mag = item.get("magnitude") or 0
    depth = item.get("depth") or 0
    lat = item.get("latitude") or 0
    lng = item.get("longitude") or 0
    place = item.get("place") or item.get("closer_towns") or "Desconocido"

    return {
        "type": "Sismo",
        "geometry": {"type": "Point", "coordinates": [lng, lat, depth]},
        "properties": {
            "value": f"{float(mag):.1f}",
            "addressFormatted": place,
            "date": date_str,
            "time": time_str,
            "depth": f"{float(depth):.1f} km",
            "lat": str(round(float(lat), 4)),
            "long": str(round(float(lng), 4)),
            "country": "Colombia/Venezuela",
            "mag_type": item.get("mag_type", ""),
            "status": item.get("status", ""),
        },
    }


@router.get("/sgc")
async def get_sgc_sismos(
    days: int = Query(default=30, ge=1, le=365),
    min_mag: float = Query(default=0.0, ge=0),
):
    """
    Sismos de SGC Colombia filtrados a la region Venezuela/borde colombiano.
    - days: cuantos dias hacia atras (default 30)
    - min_mag: magnitud minima (default 0.0)
    """
    end = datetime.now()
    start = end - timedelta(days=days)

    payload = {
        "local_time_after":  start.strftime("%Y-%m-%d %H:%M"),
        "local_time_before": end.strftime("%Y-%m-%d %H:%M"),
        "lat_min": VE_LAT_MIN,
        "lat_max": VE_LAT_MAX,
        "lon_min": VE_LON_MIN,
        "lon_max": VE_LON_MAX,
    }

    try:
        all_features = []
        async with aiohttp.ClientSession() as session:
            # Fetch page 1 to get total count
            async with session.post(
                f"{SGC_API}?page=1",
                json=payload,
                headers=SGC_HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=502, detail="Error al obtener datos de SGC")
                data = await resp.json()

            total = data.get("count", 0)
            results = data.get("results", {}).get("results", [])
            all_features += results

            # Fetch remaining pages (max 500 events total)
            import math
            total_pages = min(math.ceil(total / 100), 5)
            for page in range(2, total_pages + 1):
                async with session.post(
                    f"{SGC_API}?page={page}",
                    json=payload,
                    headers=SGC_HEADERS,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        page_data = await resp.json()
                        all_features += page_data.get("results", {}).get("results", [])

        features = [
            _transform(item) for item in all_features
            if (item.get("magnitude") or 0) >= min_mag
            and item.get("event_type", "earthquake") == "earthquake"
        ]

        return {
            "type": "FeatureCollection",
            "features": features,
            "meta": {
                "total_sgc": total,
                "returned": len(features),
                "source": "SGC Colombia",
                "period_days": days,
            },
        }

    except aiohttp.ClientError as e:
        logger.error("Error de conexion SGC: %s", e)
        raise HTTPException(status_code=502, detail="No se pudo conectar con SGC")
    except Exception as e:
        logger.error("Error SGC: %s", e)
        raise HTTPException(status_code=500, detail="Error interno")
