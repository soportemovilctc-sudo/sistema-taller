"""Punto de entrada de la aplicación FastAPI del sistema de taller."""
import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import SessionLocal
from app.deps import NoAutenticado, SinPermiso
from app.utils.flash import flash
from app import models
from app.security import hash_password

from app.routers import auth, dashboard, clientes, ordenes, tecnicos, inventario, pos, contabilidad, reportes, configuracion, api, catalogo, facturacion, servicio_rapido

app = FastAPI(title="Sistema de Taller", version="1.0.0")

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY, session_cookie="taller_session")

os.makedirs("app/static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.exception_handler(NoAutenticado)
async def no_autenticado_handler(request: Request, exc: NoAutenticado):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(SinPermiso)
async def sin_permiso_handler(request: Request, exc: SinPermiso):
    flash(request, "No tienes permisos para realizar esa acción.", "error")
    referer = request.headers.get("referer", "/")
    return RedirectResponse(referer, status_code=303)


def ejecutar_migraciones():
    """Aplica las migraciones de Alembic (crea/actualiza las tablas).
    Funciona igual en SQLite (desarrollo) y en PostgreSQL (Railway) porque
    ambas usan la misma DATABASE_URL."""
    from alembic.config import Config
    from alembic import command

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_cfg = Config(os.path.join(base_dir, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(base_dir, "alembic"))
    command.upgrade(alembic_cfg, "head")


def sembrar_datos_iniciales():
    """Crea el usuario administrador y la fila de configuración la primera
    vez que se levanta el sistema."""
    db = SessionLocal()
    try:
        if db.query(models.Usuario).count() == 0:
            admin = models.Usuario(
                username=settings.ADMIN_USERNAME.strip().lower(),
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                nombre_completo="Administrador",
                rol="admin",
                activo=True,
            )
            db.add(admin)
        if db.get(models.Configuracion, 1) is None:
            db.add(models.Configuracion(id=1, nombre_taller="Mi Taller", moneda="L", recargo_default_pct=0))
        if db.get(models.ConfiguracionFacturacion, 1) is None:
            db.add(models.ConfiguracionFacturacion(
                id=1,
                texto_legal_fiscal=(
                    "Original: Cliente / Copia: Obligado Tributario. "
                    "La factura es beneficio de todos, exijala."
                ),
                texto_legal_interno=(
                    "Este documento es un comprobante interno del taller y no es valido "
                    "como factura fiscal ante la SAR."
                ),
            ))
        sembrar_catalogo_equipos(db)
        db.commit()
    finally:
        db.close()


def sembrar_catalogo_equipos(db):
    """Carga el catálogo inicial de marcas/modelos solo si aún no existe
    ninguna marca (para no pisar lo que el usuario haya agregado o editado)."""
    from app.utils.catalogo_seed import MARCAS_SEED

    if db.query(models.MarcaEquipo).count() > 0:
        return
    for orden, (nombre_marca, modelos) in enumerate(MARCAS_SEED.items()):
        marca = models.MarcaEquipo(nombre=nombre_marca, orden=orden, activo=True)
        db.add(marca)
        db.flush()
        for nombre_modelo in modelos:
            db.add(models.ModeloEquipo(marca_id=marca.id, nombre=nombre_modelo, activo=True))


@app.on_event("startup")
def on_startup():
    ejecutar_migraciones()
    sembrar_datos_iniciales()


@app.get("/health")
def health_check():
    """Healthcheck usado por Railway para confirmar que la app está viva."""
    return {"status": "ok"}


app.include_router(dashboard.router)
app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(ordenes.router)
app.include_router(tecnicos.router)
app.include_router(inventario.router)
app.include_router(pos.router)
app.include_router(contabilidad.router)
app.include_router(reportes.router)
app.include_router(configuracion.router)
app.include_router(catalogo.router)
app.include_router(facturacion.router)
app.include_router(servicio_rapido.router)
app.include_router(api.router)
