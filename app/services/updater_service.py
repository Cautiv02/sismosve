"""
Servicio de actualizacion de datos con scheduler
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

VET = timezone(timedelta(hours=-4))
from typing import Optional

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..models.schemas import FunvisisCollection, SismosCollection
from .sismos_service import SismosService
from . import db_service


USGS_VE_URL = (
    "https://earthquake.usgs.gov/fdsnws/event/1/query"
    "?format=geojson&limit=200&orderby=time&minmagnitude=1.0"
    "&minlatitude=0.6&maxlatitude=12.5&minlongitude=-73.5&maxlongitude=-59.5"
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
            self.scheduler.add_job(
                self.update_sismos_data,
                IntervalTrigger(seconds=self.update_interval),
                id="update_sismos",
                replace_existing=True,
            )
            self.scheduler.add_job(
                self._fetch_and_save_usgs,
                IntervalTrigger(seconds=self.update_interval),
                id="update_usgs",
                replace_existing=True,
            )
            self.scheduler.start()
            self.is_running = True
            await self.update_sismos_data()
            await self._fetch_and_save_usgs()
            self.logger.info("Scheduler iniciado. Intervalo: %ds", self.update_interval)
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

    async def update_sismos_data(self) -> bool:
        self.logger.info("Actualizando FUNVISIS...")
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
                # Guardar en registro propio
                self._save_collection_to_db(sismos_data, source="FUNVISIS")
                return True

            self.update_stats["failed_updates"] += 1
            return False
        except Exception as e:
            self.logger.error("Error FUNVISIS: %s", e)
            self.update_stats["failed_updates"] += 1
            self.update_stats["last_error"] = str(e)
            return False

    async def _fetch_and_save_usgs(self):
        self.logger.info("Actualizando USGS Venezuela...")
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(USGS_VE_URL) as resp:
                    if resp.status != 200:
                        self.logger.error("USGS respondio %d", resp.status)
                        return
                    data = await resp.json()

            nuevos = 0
            for f in data.get("features", []):
                props = f.get("properties", {})
                coords = f.get("geometry", {}).get("coordinates", [0, 0, 0])
                ts = (props.get("time") or 0) / 1000
                try:
                    dt = datetime.fromtimestamp(ts, tz=VET)
                    date_str = dt.strftime("%d-%m-%Y")
                    time_str = dt.strftime("%H:%M")
                except Exception:
                    continue
                mag = props.get("mag") or 0
                if db_service.upsert_sismo(
                    source="USGS",
                    magnitude=float(mag),
                    lat=float(coords[1]),
                    lon=float(coords[0]),
                    depth=f"{float(coords[2]):.1f} km",
                    place=props.get("place") or "Venezuela",
                    date=date_str,
                    time=time_str,
                    country="Venezuela",
                ):
                    nuevos += 1

            self.logger.info("USGS: %d nuevos eventos guardados", nuevos)
        except Exception as e:
            self.logger.error("Error USGS fetch: %s", e)

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
        self.logger.info("%s: %d nuevos eventos guardados en DB", source, nuevos)

    async def force_update(self) -> bool:
        await self._fetch_and_save_usgs()
        return await self.update_sismos_data()

    def get_update_status(self) -> dict:
        return {
            "is_running": self.is_running,
            "update_interval": self.update_interval,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "stats": self.update_stats,
            "db_total": db_service.get_total(),
        }

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

    def _get_next_update_time(self) -> Optional[str]:
        if not self.is_running or not self.last_update:
            return None
        from datetime import timedelta
        return (self.last_update + timedelta(seconds=self.update_interval)).isoformat()
