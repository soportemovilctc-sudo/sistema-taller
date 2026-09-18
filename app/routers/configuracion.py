"""Configuración general del taller (nombre, logo, contacto, moneda, recargo) y QR local."""
import os
import shutil

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from io import BytesIO

from app.templates_env import templates
from app.database import get_db
from app.models import Configuracion
from app.utils.calculations import to_decimal
from app.utils.qr_local import generar_qr_png, url_acceso_local
from app.utils.flash import flash
from app.deps import login_required, roles_required

router = APIRouter()

UPLOADS_DIR = "app/static/uploads"


def get_or_create_config(db: Session) -> Configuracion:
    cfg = db.get(Configuracion, 1)
    if not cfg:
        cfg = Configuracion(id=1, nombre_taller="Mi Taller")
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("/configuracion")
def configuracion_index(request: Request, db: Session = Depends(get_db), usuario=Depends(roles_required("admin"))):
    cfg = get_or_create_config(db)
    return templates.TemplateResponse("configuracion/index.html", {
        "request": request, "config": cfg, "usuario": usuario,
        "url_local": url_acceso_local(),
    })


@router.post("/configuracion")
def configuracion_actualizar(
    request: Request,
    nombre_taller: str = Form(...), telefono: str = Form(""), whatsapp: str = Form(""),
    direccion: str = Form(""), correo: str = Form(""), moneda: str = Form("L"),
    recargo_default_pct: str = Form("0"), info_pdf_extra: str = Form(""),
    condiciones_servicio: str = Form(""),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    cfg = get_or_create_config(db)
    cfg.nombre_taller = nombre_taller.strip()
    cfg.telefono = telefono
    cfg.whatsapp = whatsapp
    cfg.direccion = direccion
    cfg.correo = correo
    cfg.moneda = moneda or "L"
    cfg.recargo_default_pct = to_decimal(recargo_default_pct or 0)
    cfg.info_pdf_extra = info_pdf_extra
    cfg.condiciones_servicio = condiciones_servicio

    if logo and logo.filename:
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        extension = os.path.splitext(logo.filename)[1] or ".png"
        destino = os.path.join(UPLOADS_DIR, f"logo{extension}")
        with open(destino, "wb") as buffer:
            shutil.copyfileobj(logo.file, buffer)
        cfg.logo_path = destino

    db.commit()
    flash(request, "Configuración guardada correctamente.", "success")
    return RedirectResponse("/configuracion", status_code=303)


@router.get("/configuracion/qr")
def configuracion_qr(usuario=Depends(roles_required("admin"))):
    url = url_acceso_local()
    png_bytes = generar_qr_png(url)
    return StreamingResponse(BytesIO(png_bytes), media_type="image/png")


@router.post("/admin/limpiar-datos-prueba")
def limpiar_datos_prueba(request: Request, db: Session = Depends(get_db), usuario=Depends(roles_required("admin"))):
    """Endpoint temporal de mantenimiento: borra el cliente/órdenes/facturas/
    marca de PRUEBA confirmados con el usuario, antes de subir a hosting.
    Se elimina de este archivo una vez ejecutado."""
    from app.models import Cliente, OrdenServicio, Factura, Pago, HistorialEstado, MarcaEquipo, ModeloEquipo

    resumen = {"clientes": 0, "ordenes": 0, "facturas": 0, "pagos": 0, "historial": 0, "marcas": 0, "modelos": 0}

    cliente = db.query(Cliente).filter(Cliente.nombre == "Cliente de Prueba").first()
    if cliente:
        ordenes = db.query(OrdenServicio).filter(OrdenServicio.cliente_id == cliente.id).all()
        orden_ids = [o.id for o in ordenes]
        if orden_ids:
            resumen["facturas"] = db.query(Factura).filter(Factura.orden_id.in_(orden_ids)).delete(synchronize_session=False)
            resumen["pagos"] = db.query(Pago).filter(Pago.orden_id.in_(orden_ids)).delete(synchronize_session=False)
            resumen["historial"] = db.query(HistorialEstado).filter(HistorialEstado.orden_id.in_(orden_ids)).delete(synchronize_session=False)
            resumen["ordenes"] = db.query(OrdenServicio).filter(OrdenServicio.id.in_(orden_ids)).delete(synchronize_session=False)
        db.delete(cliente)
        resumen["clientes"] = 1

    marca = db.query(MarcaEquipo).filter(MarcaEquipo.nombre == "MARCA DE PRUEBA").first()
    if marca:
        resumen["modelos"] = db.query(ModeloEquipo).filter(ModeloEquipo.marca_id == marca.id).delete(synchronize_session=False)
        db.delete(marca)
        resumen["marcas"] = 1

    db.commit()
    return resumen

