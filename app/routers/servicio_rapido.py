"""Plantillas de 'servicio rápido': permiten al técnico guardar combinaciones
frecuentes de falla/estado/observaciones/trabajo/plazo/precio y aplicarlas con
un clic al crear o editar una orden, sin perder los demás datos ya escritos
en el formulario (por eso estos endpoints responden JSON y se consumen con
fetch() desde orden.js, en vez de recargar la página)."""
from decimal import InvalidOperation

from fastapi import APIRouter, Depends, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ServicioRapido
from app.deps import login_required
from app.utils.calculations import to_decimal

router = APIRouter()


def _validar_datos(nombre: str, dias_plazo, cotizacion, recargo_pct):
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre del servicio rápido no puede estar vacío.")
    try:
        dias = int(dias_plazo or 0)
    except (TypeError, ValueError):
        raise ValueError("El plazo en días debe ser un número entero.")
    if dias < 0:
        raise ValueError("El plazo en días no puede ser negativo.")
    try:
        cot = to_decimal(cotizacion or 0)
        pct = to_decimal(recargo_pct or 0)
    except InvalidOperation:
        raise ValueError("La cotización y el recargo deben ser números válidos.")
    if cot < 0 or pct < 0:
        raise ValueError("La cotización y el recargo no pueden ser negativos.")
    return nombre, dias, cot, pct


@router.get("/servicios-rapidos")
def servicios_rapidos_listar(db: Session = Depends(get_db), usuario=Depends(login_required)):
    servicios = db.query(ServicioRapido).order_by(ServicioRapido.orden, ServicioRapido.nombre).all()
    return JSONResponse({"ok": True, "servicios": [s.a_dict() for s in servicios]})


@router.post("/servicios-rapidos")
def servicios_rapidos_crear(
    nombre: str = Form(...),
    falla_reportada: str = Form(""),
    estado_fisico: str = Form(""),
    observaciones: str = Form(""),
    trabajo_realizado: str = Form(""),
    dias_plazo: str = Form("0"),
    cotizacion: str = Form("0"),
    recargo_pct: str = Form("0"),
    db: Session = Depends(get_db),
    usuario=Depends(login_required),
):
    try:
        nombre, dias, cot, pct = _validar_datos(nombre, dias_plazo, cotizacion, recargo_pct)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    existente = db.query(ServicioRapido).filter(ServicioRapido.nombre.ilike(nombre)).first()
    if existente:
        return JSONResponse({"ok": False, "error": f'Ya existe un servicio rápido llamado "{nombre}".'}, status_code=400)

    maximo_orden = db.query(ServicioRapido).count()
    servicio = ServicioRapido(
        nombre=nombre, falla_reportada=falla_reportada, estado_fisico=estado_fisico,
        observaciones=observaciones, trabajo_realizado=trabajo_realizado,
        dias_plazo=dias, cotizacion=cot, recargo_pct=pct, orden=maximo_orden,
    )
    db.add(servicio)
    db.commit()
    return JSONResponse({"ok": True, "servicio": servicio.a_dict()})


@router.post("/servicios-rapidos/{servicio_id}/editar")
def servicios_rapidos_editar(
    servicio_id: int,
    nombre: str = Form(...),
    falla_reportada: str = Form(""),
    estado_fisico: str = Form(""),
    observaciones: str = Form(""),
    trabajo_realizado: str = Form(""),
    dias_plazo: str = Form("0"),
    cotizacion: str = Form("0"),
    recargo_pct: str = Form("0"),
    db: Session = Depends(get_db),
    usuario=Depends(login_required),
):
    servicio = db.get(ServicioRapido, servicio_id)
    if not servicio:
        return JSONResponse({"ok": False, "error": "Servicio rápido no encontrado."}, status_code=404)
    try:
        nombre, dias, cot, pct = _validar_datos(nombre, dias_plazo, cotizacion, recargo_pct)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    duplicado = db.query(ServicioRapido).filter(
        ServicioRapido.nombre.ilike(nombre), ServicioRapido.id != servicio_id
    ).first()
    if duplicado:
        return JSONResponse({"ok": False, "error": f'Ya existe un servicio rápido llamado "{nombre}".'}, status_code=400)

    servicio.nombre = nombre
    servicio.falla_reportada = falla_reportada
    servicio.estado_fisico = estado_fisico
    servicio.observaciones = observaciones
    servicio.trabajo_realizado = trabajo_realizado
    servicio.dias_plazo = dias
    servicio.cotizacion = cot
    servicio.recargo_pct = pct
    db.commit()
    return JSONResponse({"ok": True, "servicio": servicio.a_dict()})


@router.post("/servicios-rapidos/{servicio_id}/eliminar")
def servicios_rapidos_eliminar(
    servicio_id: int, db: Session = Depends(get_db), usuario=Depends(login_required),
):
    servicio = db.get(ServicioRapido, servicio_id)
    if not servicio:
        return JSONResponse({"ok": False, "error": "Servicio rápido no encontrado."}, status_code=404)
    db.delete(servicio)
    db.commit()
    return JSONResponse({"ok": True, "id": servicio_id})
