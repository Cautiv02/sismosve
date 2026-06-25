"""
AplicaciÃ³n principal FastAPI para sismos de Venezuela - Modular
"""

import traceback
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

from .config import lifespan
from .routers import sismos, admin, seo, usgs_router, sgc_router, registro_router
# from .exceptions import not_found_handler, jinja_undefined_handler, internal_error_handler


# Crear aplicaciÃ³n FastAPI
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
    """PÃ¡gina principal de la aplicaciÃ³n"""
    response = templates.TemplateResponse(request, "index.html")

    # Headers para evitar cachÃ© del HTML principal (siempre obtener la versiÃ³n mÃ¡s reciente)
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



@app.get("/sgc", response_class=HTMLResponse, include_in_schema=False)
async def sgc_page(request: Request):
    """Pagina de sismos SGC Colombia filtrados a Venezuela"""
    response = templates.TemplateResponse(request, "sgc.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
@app.get("/usgs", response_class=HTMLResponse, include_in_schema=False)
async def usgs_page(request: Request):
    """Pagina de sismos mundiales USGS"""
    response = templates.TemplateResponse(request, "usgs.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
app.include_router(sismos.router)
app.include_router(admin.router)
app.include_router(seo.router)
app.include_router(usgs_router.router)
app.include_router(sgc_router.router)
app.include_router(registro_router.router)

# Configurar manejadores de excepciones (por implementar)
# app.add_exception_handler(UndefinedError, jinja_undefined_handler)

# Configurar archivos estÃ¡ticos
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info"
    )


