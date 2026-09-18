"""Módulo de órdenes de servicio: creación, edición, estados, abonos y PDF."""
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from io import BytesIO

from app.templates_env import templates
from app.database import get_db
from app.models import (
    OrdenServicio, Cliente, Tecnico, HistorialEstado, Pago, Configuracion,
    TIPOS_EQUIPO, ESTADOS_ORDEN, PRIORIDADES, FORMAS_PAGO,
    ACCESORIOS_DISPONIBLES, CONDICIONES_FISICAS, MarcaEquipo, ServicioRapido,
)
from app.utils.numbering import generar_numero_orden
from app.utils.calculations import calcular_recargo, calcular_total, calcular_saldo, validar_abono, to_decimal, recalcular_orden
from app.utils.pdf import generar_pdf_orden, construir_contexto_pdf
from app.utils.pdf_ticket import generar_ticket_orden
from app.utils.flash import flash
from app.deps import login_required

router = APIRouter()


def _opciones_formulario(db: Session):
    marcas_catalogo = (
        db.query(MarcaEquipo)
        .filter(MarcaEquipo.activo == True)  # noqa: E712
        .order_by(MarcaEquipo.orden, MarcaEquipo.nombre)
        .all()
    )
    marca_modelos_map = {
        m.nombre: sorted([mo.nombre for mo in m.modelos if mo.activo])
        for m in marcas_catalogo
    }
    servicios_rapidos = (
        db.query(ServicioRapido).order_by(ServicioRapido.orden, ServicioRapido.nombre).all()
    )
    return {
        "clientes": db.query(Cliente).order_by(Cliente.nombre).all(),
        "tecnicos": db.query(Tecnico).filter(Tecnico.activo == True).order_by(Tecnico.nombre).all(),  # noqa: E712
        "tipos_equipo": TIPOS_EQUIPO,
        "estados": ESTADOS_ORDEN,
        "prioridades": PRIORIDADES,
        "formas_pago": FORMAS_PAGO,
        "accesorios_disponibles": ACCESORIOS_DISPONIBLES,
        "condiciones_disponibles": CONDICIONES_FISICAS,
        "marcas_catalogo": marcas_catalogo,
        "marca_modelos_map": marca_modelos_map,
        "servicios_rapidos": [s.a_dict() for s in servicios_rapidos],
    }


def _config(db: Session) -> Configuracion:
    cfg = db.get(Configuracion, 1)
    return cfg


@router.get("/ordenes")
def ordenes_list(
    request: Request, q: str = "", estado: str = "", tecnico_id: str = "", prioridad: str = "",
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    query = db.query(OrdenServicio).options(joinedload(OrdenServicio.cliente), joinedload(OrdenServicio.tecnico))
    if q:
        like = f"%{q}%"
        query = query.join(Cliente).filter(or_(
            OrdenServicio.numero_orden.ilike(like), Cliente.nombre.ilike(like),
            Cliente.telefono.ilike(like), Cliente.whatsapp.ilike(like), Cliente.dni.ilike(like),
            OrdenServicio.imei.ilike(like), OrdenServicio.numero_serie.ilike(like),
            OrdenServicio.marca.ilike(like), OrdenServicio.modelo.ilike(like),
        ))
    if estado:
        query = query.filter(OrdenServicio.estado == estado)
    if tecnico_id:
        query = query.filter(OrdenServicio.tecnico_id == int(tecnico_id))
    if prioridad:
        query = query.filter(OrdenServicio.prioridad == prioridad)

    ordenes = query.order_by(OrdenServicio.fecha.desc()).all()
    opciones = _opciones_formulario(db)
    return templates.TemplateResponse("ordenes/list.html", {
        "request": request, "ordenes": ordenes, "usuario": usuario,
        "q": q, "estado": estado, "tecnico_id": tecnico_id, "prioridad": prioridad,
        **opciones,
    })


@router.get("/ordenes/nueva")
def ordenes_nueva_form(request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    cfg = _config(db)
    return templates.TemplateResponse("ordenes/form.html", {
        "request": request, "orden": None, "usuario": usuario,
        "recargo_default": cfg.recargo_default_pct if cfg else 0,
        **_opciones_formulario(db),
    })


@router.post("/ordenes/nueva")
def ordenes_crear(
    request: Request,
    cliente_id: int = Form(...),
    tecnico_id: str = Form(""),
    tipo_equipo: str = Form("Celular"),
    marca: str = Form(""),
    modelo: str = Form(""),
    imei: str = Form(""),
    numero_serie: str = Form(""),
    accesorios: list[str] = Form([]),
    condicion: list[str] = Form([]),
    observaciones_condicion: str = Form(""),
    falla_reportada: str = Form(""),
    diagnostico: str = Form(""),
    trabajo_realizado: str = Form(""),
    observaciones: str = Form(""),
    prioridad: str = Form("Normal"),
    estado: str = Form("RECIBIDO"),
    pin: str = Form(""),
    patron: str = Form(""),
    cotizacion: str = Form("0"),
    recargo_pct: str = Form("0"),
    forma_pago: str = Form("Efectivo"),
    fecha_entrega: str = Form(""),
    db: Session = Depends(get_db),
    usuario=Depends(login_required),
):
    try:
        cot = to_decimal(cotizacion or 0)
        pct = to_decimal(recargo_pct or 0)
        recargo = calcular_recargo(cot, pct)
        total = calcular_total(cot, recargo)
    except ValueError as e:
        flash(request, str(e), "error")
        return RedirectResponse("/ordenes/nueva", status_code=303)

    orden = OrdenServicio(
        numero_orden=generar_numero_orden(db),
        cliente_id=cliente_id,
        tecnico_id=int(tecnico_id) if tecnico_id else None,
        tipo_equipo=tipo_equipo, marca=marca, modelo=modelo, imei=imei, numero_serie=numero_serie,
        accesorios=",".join(accesorios), condicion_fisica=",".join(condicion),
        observaciones_condicion=observaciones_condicion,
        falla_reportada=falla_reportada, diagnostico=diagnostico, trabajo_realizado=trabajo_realizado,
        observaciones=observaciones, prioridad=prioridad, estado=estado,
        pin=pin or None, patron=patron or None,
        cotizacion=cot, recargo_pct=pct, recargo_monto=recargo, total=total, abonado=Decimal("0"), saldo=total,
        forma_pago=forma_pago,
        fecha_entrada=date.today(),
        fecha_entrega=datetime.strptime(fecha_entrega, "%Y-%m-%d").date() if fecha_entrega else None,
    )
    db.add(orden)
    db.flush()

    historial = HistorialEstado(orden_id=orden.id, estado_anterior=None, estado_nuevo=estado,
                                 usuario_nombre=usuario["nombre_completo"], observacion="Orden creada")
    db.add(historial)
    db.commit()
    flash(request, f"Orden {orden.numero_orden} creada correctamente.", "success")
    return RedirectResponse(f"/ordenes/{orden.id}", status_code=303)


@router.get("/ordenes/{orden_id}")
def ordenes_detalle(orden_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        flash(request, "Orden no encontrada.", "error")
        return RedirectResponse("/ordenes", status_code=303)
    opciones = _opciones_formulario(db)
    return templates.TemplateResponse("ordenes/detail.html", {
        "request": request, "orden": orden, "usuario": usuario, **opciones,
    })


@router.get("/ordenes/{orden_id}/editar")
def ordenes_editar_form(orden_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        flash(request, "Orden no encontrada.", "error")
        return RedirectResponse("/ordenes", status_code=303)
    return templates.TemplateResponse("ordenes/form.html", {
        "request": request, "orden": orden, "usuario": usuario,
        "recargo_default": orden.recargo_pct,
        **_opciones_formulario(db),
    })


@router.post("/ordenes/{orden_id}/editar")
def ordenes_actualizar(
    orden_id: int,
    request: Request,
    cliente_id: int = Form(...),
    tecnico_id: str = Form(""),
    tipo_equipo: str = Form("Celular"),
    marca: str = Form(""),
    modelo: str = Form(""),
    imei: str = Form(""),
    numero_serie: str = Form(""),
    accesorios: list[str] = Form([]),
    condicion: list[str] = Form([]),
    observaciones_condicion: str = Form(""),
    falla_reportada: str = Form(""),
    diagnostico: str = Form(""),
    trabajo_realizado: str = Form(""),
    observaciones: str = Form(""),
    prioridad: str = Form("Normal"),
    pin: str = Form(""),
    patron: str = Form(""),
    cotizacion: str = Form("0"),
    recargo_pct: str = Form("0"),
    forma_pago: str = Form("Efectivo"),
    fecha_entrega: str = Form(""),
    db: Session = Depends(get_db),
    usuario=Depends(login_required),
):
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        return RedirectResponse("/ordenes", status_code=303)
    try:
        orden.cotizacion = to_decimal(cotizacion or 0)
        orden.recargo_pct = to_decimal(recargo_pct or 0)
        if orden.cotizacion < 0 or orden.recargo_pct < 0:
            raise ValueError("La cotización y el recargo no pueden ser negativos.")
    except (InvalidOperation, ValueError) as e:
        flash(request, str(e), "error")
        return RedirectResponse(f"/ordenes/{orden_id}/editar", status_code=303)

    orden.cliente_id = cliente_id
    orden.tecnico_id = int(tecnico_id) if tecnico_id else None
    orden.tipo_equipo = tipo_equipo
    orden.marca = marca
    orden.modelo = modelo
    orden.imei = imei
    orden.numero_serie = numero_serie
    orden.accesorios = ",".join(accesorios)
    orden.condicion_fisica = ",".join(condicion)
    orden.observaciones_condicion = observaciones_condicion
    orden.falla_reportada = falla_reportada
    orden.diagnostico = diagnostico
    orden.trabajo_realizado = trabajo_realizado
    orden.observaciones = observaciones
    orden.prioridad = prioridad
    orden.pin = pin or None
    orden.patron = patron or None
    orden.forma_pago = forma_pago
    orden.fecha_entrega = datetime.strptime(fecha_entrega, "%Y-%m-%d").date() if fecha_entrega else None

    recalcular_orden(orden)
    db.commit()
    flash(request, "Orden actualizada correctamente.", "success")
    return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)


@router.post("/ordenes/{orden_id}/estado")
def ordenes_cambiar_estado(
    orden_id: int, request: Request,
    nuevo_estado: str = Form(...), observacion: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    orden = db.get(OrdenServicio, orden_id)
    if orden and nuevo_estado in ESTADOS_ORDEN:
        historial = HistorialEstado(
            orden_id=orden.id, estado_anterior=orden.estado, estado_nuevo=nuevo_estado,
            usuario_nombre=usuario["nombre_completo"], observacion=observacion,
        )
        orden.estado = nuevo_estado
        db.add(historial)
        db.commit()
        flash(request, f"Estado actualizado a {nuevo_estado}.", "success")
    return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)


@router.post("/ordenes/{orden_id}/abono")
def ordenes_registrar_abono(
    orden_id: int, request: Request,
    monto: str = Form(...), forma_pago: str = Form("Efectivo"), observacion: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        return RedirectResponse("/ordenes", status_code=303)
    try:
        monto_validado = validar_abono(monto, orden.saldo)
    except (ValueError, InvalidOperation) as e:
        flash(request, str(e), "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    pago = Pago(orden_id=orden.id, monto=monto_validado, forma_pago=forma_pago,
                usuario_nombre=usuario["nombre_completo"], observacion=observacion)
    db.add(pago)
    db.flush()
    db.refresh(orden)
    recalcular_orden(orden)
    db.commit()
    flash(request, f"Abono de {monto_validado} registrado correctamente.", "success")
    return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)


def _generar_pdf_bytes(db: Session, orden_id: int):
    orden = db.get(OrdenServicio, orden_id)
    cfg = _config(db)
    contexto = construir_contexto_pdf(orden, cfg)
    return orden, generar_pdf_orden(contexto)


@router.get("/ordenes/{orden_id}/pdf")
def ordenes_pdf_ver(orden_id: int, db: Session = Depends(get_db), usuario=Depends(login_required)):
    orden, pdf_bytes = _generar_pdf_bytes(db, orden_id)
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf",
                              headers={"Content-Disposition": f'inline; filename="{orden.numero_orden}.pdf"'})


@router.get("/ordenes/{orden_id}/pdf/descargar")
def ordenes_pdf_descargar(orden_id: int, db: Session = Depends(get_db), usuario=Depends(login_required)):
    orden, pdf_bytes = _generar_pdf_bytes(db, orden_id)
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf",
                              headers={"Content-Disposition": f'attachment; filename="{orden.numero_orden}.pdf"'})


@router.get("/ordenes/{orden_id}/pdf/tirilla")
def ordenes_tirilla_ver(orden_id: int, db: Session = Depends(get_db), usuario=Depends(login_required)):
    orden = db.get(OrdenServicio, orden_id)
    cfg = _config(db)
    contexto = construir_contexto_pdf(orden, cfg)
    pdf_bytes = generar_ticket_orden(contexto)
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf",
                              headers={"Content-Disposition": f'inline; filename="{orden.numero_orden}_tirilla.pdf"'})


@router.get("/ordenes/{orden_id}/pdf/tirilla/descargar")
def ordenes_tirilla_descargar(orden_id: int, db: Session = Depends(get_db), usuario=Depends(login_required)):
    orden = db.get(OrdenServicio, orden_id)
    cfg = _config(db)
    contexto = construir_contexto_pdf(orden, cfg)
    pdf_bytes = generar_ticket_orden(contexto)
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf",
                              headers={"Content-Disposition": f'attachment; filename="{orden.numero_orden}_tirilla.pdf"'})


@router.get("/ordenes/{orden_id}/whatsapp")
def ordenes_whatsapp(orden_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    """Genera el PDF y muestra un enlace de WhatsApp con el resumen (el archivo
    se debe adjuntar manualmente, WhatsApp Web no permite adjuntar por enlace)."""
    orden = db.get(OrdenServicio, orden_id)
    mensaje = (
        f"Hola {orden.cliente.nombre if orden.cliente else ''}, aquí está el resumen de tu orden "
        f"{orden.numero_orden}: Estado {orden.estado}, Total L{orden.total}, Saldo pendiente L{orden.saldo}."
    )
    telefono = (orden.cliente.whatsapp or orden.cliente.telefono or "") if orden.cliente else ""
    telefono_limpio = "".join(ch for ch in telefono if ch.isdigit())
    import urllib.parse
    link = f"https://wa.me/{telefono_limpio}?text={urllib.parse.quote(mensaje)}"
    return RedirectResponse(link, status_code=303)
