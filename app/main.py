"""
Aplicación principal FastAPI para sismos de Venezuela - Modular
"""

import traceback
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

from .config import lifespan
from .routers import sismos, admin, seo
# from .exceptions import not_found_handler, jinja_undefined_handler, internal_error_handler


# Crear aplicación FastAPI
app = FastAPI(
    title="SismosVE API",
    description="API para datos de sismos de Venezuela desde FUNVISIS",
    version="1.0.0",
    lifespan=lifespan,
)

# Configurar templates (cache_size=0 evita bug con Python 3.14)
_jinja_env = Environment(loader=FileSystemLoader("templates"), cache_size=0)
templates = Jinja2Templates(env=_jinja_env)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home(request: Request):
    """Página principal de la aplicación"""
    response = templates.TemplateResponse(request, "index.html")

    # Headers para evitar caché del HTML principal (siempre obtener la versión más reciente)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    print("=== ERROR ===")
    print(tb)
    return PlainTextResponse(tb, status_code=500)

# Incluir routers
app.include_router(sismos.router)
app.include_router(admin.router)
app.include_router(seo.router)

# Configurar manejadores de excepciones (por implementar)
# app.add_exception_handler(UndefinedError, jinja_undefined_handler)

# Configurar archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info"
    )