"""
Bot de ingesta sismica - feeds GeoJSON USGS + EMSC FDSNWS + FUNVISIS
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..models.schemas import FunvisisCollection, SismosCollection
from .sismos_service import SismosService
from . import db_service

VET = timezone(timedelta(hours=-4))

# --- Venezuela bounding box ---
VE_MINLAT, VE_MAXLAT =  0.6, 12.5
VE_MINLON, VE_MAXLON = -73.5, -59.5

def _in_venezuela(lat: float, lon: float) -> bool:
    return VE_MINLAT <= lat <= VE_MAXLAT and VE_MINLON <= lon <= VE_MAXLON

# --- USGS GeoJSON feeds (pregenerados, sin limite de registros) ---
USGS_FEED_HOUR  = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"
USGS_FEED_DAY   = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
USGS_FEED_WEEK  = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson"
USGS_FEED_MONTH = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/1.0_month.geojson"

# --- EMSC FDSNWS (complemento regional) ---
EMSC_VE_URL = (
    "https://www.seismicportal.eu/fdsnws/event/1/query"
    "?format=json&limit=1000&orderby=time&minmagnitude=1.0"
    f"&minlatitude={VE_MINLAT}&maxlatitude={VE_MAXLAT}"
    f"&minlongitude={VE_MINLON}&maxlongitude={VE_MAXLON}"
)
EMSC_VE_URL_30D = (
    "https://www.seismicportal.eu/fdsnws/event/1/query"
    "?format=json&limit=2000&orderby=time&minmagnitude=1.0"
    f"&minlatitude={VE_MINLAT}&maxlatitude={VE_MAXLAT}"
    f"&minlongitude={VE_MINLON}&maxlongitude={VE_MAXLON}"
    "&starttime={start}&endtime={end}"
)


class UpdaterService:
    def __init__(self, sismos_service: SismosService, update_interval: int = 300):
        self.sismos_service = sismos_service
        self.update_interval = update_interval
        self.funvisis_url = "http://www.funvisis.gob.ve/maravilla.json"
        self.scheduler = AsyncIOScheduler()
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self.last_update = None
        self.update_stats = {
            "total_updates": 0,
            "successful_updates": 0,
            "failed_updates": 0,
            "last_error": None,
        }

    async def start_scheduler(self):
        if self.is_running:
            return

        db_service.init_db()

        try:
            # FUNVISIS cada 5 min
            self.scheduler.add_job(
                self.update_sismos_data,
                IntervalTrigger(seconds=self.update_interval),
                id="update_funvisis",
                replace_existing=True,
            )
            # Feed horario USGS cada 60 segundos (feed se actualiza cada 1 min)
            self.scheduler.add_job(
                self._fetch_usgs_feed_hour,
                IntervalTrigger(seconds=60),
                id="update_usgs_hour",
                replace_existing=True,
            )
            # Feed diario USGS cada 10 min (cubre huecos del horario)
            self.scheduler.add_job(
                self._fetch_usgs_feed_day,
                IntervalTrigger(seconds=600),
                id="update_usgs_day",
                replace_existing=True,
            )
            # EMSC cada 5 min
            self.scheduler.add_job(
                self._fetch_and_save_emsc,
                IntervalTrigger(seconds=self.update_interval),
                id="update_emsc",
                replace_existing=True,
            )

            self.scheduler.start()
            self.is_running = True

            # Carga inicial: arrancar con FUNVISIS y feeds históricos
            await self.update_sismos_data()
            await self._fetch_usgs_feed_month()   # historial 30 dias completo
            await self._fetch_and_save_emsc_historical()
            await self._fetch_usgs_feed_week()    # semana para asegurar recientes

            self.logger.info("Bot sismico iniciado. USGS feed cada 60s, EMSC/FUNVISIS cada %ds", self.update_interval)
        except Exception as e:
            self.logger.error("Error al iniciar scheduler: %s", e)
            raise

    async def stop_scheduler(self):
        if not self.is_running:
            return
        try:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
        except Exception as e:
            self.logger.error("Error al detener scheduler: %s", e)

    # ------------------------------------------------------------------ #
    #  USGS GeoJSON Feeds                                                  #
    # ------------------------------------------------------------------ #

    def _parse_usgs_features(self, features: list) -> int:
        """Filtra por Venezuela e inserta. Retorna nuevos guardados."""
        nuevos = 0
        for f in features:
            props  = f.get("properties", {})
            coords = f.get("geometry", {}).get("coordinates", [0, 0, 0])
            try:
                lat = float(coords[1])
                lon = float(coords[0])
            except (TypeError, ValueError):
                continue
            if not _in_venezuela(lat, lon):
                continue
            ts = (props.get("time") or 0) / 1000
            try:
                dt       = datetime.fromtimestamp(ts, tz=VET)
                date_str = dt.strftime("%d-%m-%Y")
                time_str = dt.strftime("%H:%M")
            except Exception:
                continue
            mag   = props.get("mag") or 0
            depth = coords[2] if len(coords) > 2 else 0
            if db_service.upsert_sismo(
                source="USGS",
                magnitude=float(mag),
                lat=lat,
                lon=lon,
                depth=f"{float(depth):.1f} km",
                place=props.get("place") or "Venezuela",
                date=date_str,
                time=time_str,
                country="Venezuela",
            ):
                nuevos += 1
        return nuevos

    async def _fetch_usgs_feed(self, url: str, label: str, timeout_s: int = 60) -> int:
        try:
            timeout = aiohttp.ClientTimeout(total=timeout_s)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        self.logger.error("USGS %s respondio %d", label, resp.status)
                        return 0
                    data = await resp.json(content_type=None)
            nuevos = self._parse_usgs_features(data.get("features", []))
            self.logger.info("USGS %s: %d nuevos (%d totales en feed)", label, nuevos, len(data.get("features", [])))
            return nuevos
        except Exception as e:
            self.logger.error("Error USGS %s: %s", label, e)
            return 0

    async def _fetch_usgs_feed_hour(self):
        await self._fetch_usgs_feed(USGS_FEED_HOUR, "hora", timeout_s=20)

    async def _fetch_usgs_feed_day(self):
        await self._fetch_usgs_feed(USGS_FEED_DAY, "dia", timeout_s=30)

    async def _fetch_usgs_feed_week(self):
        await self._fetch_usgs_feed(USGS_FEED_WEEK, "semana", timeout_s=60)

    async def _fetch_usgs_feed_month(self):
        self.logger.info("Cargando feed USGS mes completo (puede tardar)...")
        await self._fetch_usgs_feed(USGS_FEED_MONTH, "mes", timeout_s=120)

    # ------------------------------------------------------------------ #
    #  EMSC FDSNWS                                                         #
    # ------------------------------------------------------------------ #

    def _parse_emsc_features(self, features: list, source: str) -> int:
        nuevos = 0
        for f in features:
            props  = f.get("properties", {})
            coords = f.get("geometry", {}).get("coordinates", [0, 0, 0])
            raw_time = props.get("time") or props.get("lastupdate") or ""
            try:
                if isinstance(raw_time, (int, float)):
                    dt = datetime.fromtimestamp(float(raw_time), tz=VET)
                else:
                    dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00")).astimezone(VET)
                date_str = dt.strftime("%d-%m-%Y")
                time_str = dt.strftime("%H:%M")
            except Exception:
                continue
            mag   = props.get("mag") or props.get("magnitude") or 0
            depth = coords[2] if len(coords) > 2 else 0
            place = props.get("place") or props.get("flynn_region") or "Venezuela"
            if db_service.upsert_sismo(
                source=source,
                magnitude=float(mag),
                lat=float(coords[1]),
                lon=float(coords[0]),
                depth=f"{float(depth):.1f} km",
                place=place,
                date=date_str,
                time=time_str,
                country="Venezuela",
            ):
                nuevos += 1
        return nuevos

    async def _fetch_and_save_emsc_historical(self):
        end   = datetime.now(tz=timezone.utc)
        start = end - timedelta(days=30)
        url   = EMSC_VE_URL_30D.format(
            start=start.strftime("%Y-%m-%dT%H:%M:%S"),
            end=end.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self.logger.info("Cargando historial EMSC 30 dias...")
        try:
            timeout = aiohttp.ClientTimeout(total=90)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        self.logger.error("EMSC historico respondio %d", resp.status)
                        return
                    data = await resp.json(content_type=None)
            nuevos = self._parse_emsc_features(data.get("features", []), "EMSC")
            self.logger.info("EMSC historico: %d nuevos eventos", nuevos)
        except Exception as e:
            self.logger.error("Error EMSC historico: %s", e)

    async def _fetch_and_save_emsc(self):
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(EMSC_VE_URL) as resp:
                    if resp.status != 200:
                        self.logger.error("EMSC respondio %d", resp.status)
                        return
                    data = await resp.json(content_type=None)
            nuevos = self._parse_emsc_features(data.get("features", []), "EMSC")
            self.logger.info("EMSC: %d nuevos eventos", nuevos)
        except Exception as e:
            self.logger.error("Error EMSC: %s", e)

    # ------------------------------------------------------------------ #
    #  FUNVISIS                                                            #
    # ------------------------------------------------------------------ #

    async def update_sismos_data(self) -> bool:
        self.update_stats["total_updates"] += 1
        try:
            funvisis_data = await self._download_funvisis_data()
            if not funvisis_data:
                self.update_stats["failed_updates"] += 1
                return False
            sismos_data = self.sismos_service.transform_funvisis_to_sismos(funvisis_data)
            if self.sismos_service.save_sismos(sismos_data):
                self.update_stats["successful_updates"] += 1
                self.last_update = datetime.now()
                self._save_collection_to_db(sismos_data, source="FUNVISIS")
                return True
            self.update_stats["failed_updates"] += 1
            return False
        except Exception as e:
            self.logger.error("Error FUNVISIS: %s", e)
            self.update_stats["failed_updates"] += 1
            self.update_stats["last_error"] = str(e)
            return False

    def _save_collection_to_db(self, sismos: SismosCollection, source: str):
        nuevos = 0
        for s in sismos.features:
            p = s.properties
            try:
                lat = float(p.lat)
                lon = float(p.long)
                mag = float(p.value)
            except Exception:
                continue
            if db_service.upsert_sismo(
                source=source,
                magnitude=mag,
                lat=lat,
                lon=lon,
                depth=p.depth,
                place=p.addressFormatted,
                date=p.date,
                time=p.time,
                country=p.country,
            ):
                nuevos += 1
        self.logger.info("%s: %d nuevos eventos en DB", source, nuevos)

    async def _download_funvisis_data(self) -> Optional[FunvisisCollection]:
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.funvisis_url, headers=headers) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                        except Exception:
                            import json
                            data = json.loads(await response.text())
                        return FunvisisCollection(**data)
                    self.logger.error("HTTP %d desde FUNVISIS", response.status)
                    return None
        except asyncio.TimeoutError:
            self.logger.error("Timeout FUNVISIS")
            return None
        except Exception as e:
            self.logger.error("Error descarga FUNVISIS: %s", e)
            return None

    # ------------------------------------------------------------------ #
    #  Utils                                                               #
    # ------------------------------------------------------------------ #

    async def force_update(self) -> bool:
        await self._fetch_usgs_feed_day()
        await self._fetch_and_save_emsc()
        return await self.update_sismos_data()

    def get_update_status(self) -> dict:
        return {
            "is_running": self.is_running,
            "update_interval": self.update_interval,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "stats": self.update_stats,
            "db_total": db_service.get_total(),
        }
