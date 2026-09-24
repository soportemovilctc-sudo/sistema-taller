"""Módulo de facturación: configuración (interna y fiscal SAR-Honduras),
generación de facturas a partir de órdenes de servicio, listado, PDF
(carta y tirilla 80mm) y anulación."""
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from io import BytesIO

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.templates_env import templates
from app.database import get_db
from app.models import Factura, ConfiguracionFacturacion, Configuracion, OrdenServicio
from app.deps import login_required, roles_required
from app.utils.flash import flash
from app.utils.calculations import to_decimal
from app.utils.numbering import generar_numero_factura, extraer_correlativo_de_rango
from app.utils.pdf import generar_pdf_factura, construir_contexto_pdf_factura
from app.utils.pdf_ticket import generar_ticket_factura

router = APIRouter()


def get_or_create_cfg_facturacion(db: Session) -> ConfiguracionFacturacion:
    cfg = db.get(ConfiguracionFacturacion, 1)
    if not cfg:
        cfg = ConfiguracionFacturacion(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _config_general(db: Session) -> Configuracion:
    return db.get(Configuracion, 1)


def facturas_fiscales_restantes(cfg: ConfiguracionFacturacion) -> int | None:
    """Cuántas facturas fiscales quedan disponibles dentro del rango
    autorizado por la SAR. None si aún no hay rango configurado."""
    if not cfg or not cfg.rango_autorizado_fin:
        return None
    limite = extraer_correlativo_de_rango(cfg.rango_autorizado_fin)
    if limite is None:
        return None
    siguiente = (cfg.correlativo_fiscal_actual or 0) + 1
    return max(limite - siguiente + 1, 0)


# ---------------------------------------------------------------------------
# Configuración de facturación
# ---------------------------------------------------------------------------
@router.get("/configuracion/facturacion")
def configuracion_facturacion_index(request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    cfg = get_or_create_cfg_facturacion(db)
    return templates.TemplateResponse("configuracion/facturacion.html", {
        "request": request, "cfg": cfg, "usuario": usuario,
        "restantes_fiscal": facturas_fiscales_restantes(cfg),
    })


@router.post("/configuracion/facturacion")
def configuracion_facturacion_actualizar(
    request: Request,
    tipo_documento_default: str = Form("interno"),
    rtn_taller: str = Form(""),
    razon_social: str = Form(""),
    nombre_comercial: str = Form(""),
    domicilio_fiscal: str = Form(""),
    cai: str = Form(""),
    establecimiento: str = Form("001"),
    punto_emision: str = Form("001"),
    tipo_documento_codigo: str = Form("01"),
    rango_autorizado_inicio: str = Form(""),
    rango_autorizado_fin: str = Form(""),
    fecha_limite_emision: str = Form(""),
    alerta_umbral_fiscal: str = Form("50"),
    correlativo_fiscal_manual: str = Form(""),
    isv_tasa: str = Form("15"),
    servicios_exentos_default: bool = Form(False),
    prefijo_interno: str = Form("REC"),
    texto_legal_fiscal: str = Form(""),
    texto_legal_interno: str = Form(""),
    db: Session = Depends(get_db),
    usuario=Depends(roles_required("admin")),
):
    cfg = get_or_create_cfg_facturacion(db)
    cfg.tipo_documento_default = tipo_documento_default if tipo_documento_default in ("interno", "fiscal") else "interno"
    cfg.rtn_taller = rtn_taller.strip()
    cfg.razon_social = razon_social.strip()
    cfg.nombre_comercial = nombre_comercial.strip()
    cfg.domicilio_fiscal = domicilio_fiscal.strip()
    cfg.cai = cai.strip()
    cfg.establecimiento = establecimiento.strip() or "001"
    cfg.punto_emision = punto_emision.strip() or "001"
    cfg.tipo_documento_codigo = tipo_documento_codigo.strip() or "01"
    cfg.rango_autorizado_inicio = rango_autorizado_inicio.strip()
    cfg.rango_autorizado_fin = rango_autorizado_fin.strip()
    cfg.fecha_limite_emision = datetime.strptime(fecha_limite_emision, "%Y-%m-%d").date() if fecha_limite_emision else None
    try:
        cfg.alerta_umbral_fiscal = max(int(alerta_umbral_fiscal), 1)
    except (ValueError, TypeError):
        cfg.alerta_umbral_fiscal = 50

    # Permite al admin fijar (o corregir) desde qué número fiscal debe
    # continuar el sistema, para hacerlo coincidir con el rango real que
    # entregó la SAR. Campo opcional: si se deja vacío, no se toca el
    # correlativo actual.
    error_correlativo = None
    valor_manual = correlativo_fiscal_manual.strip()
    if valor_manual:
        try:
            nuevo_siguiente = int(valor_manual)
        except (ValueError, TypeError):
            nuevo_siguiente = None
        if nuevo_siguiente is None or nuevo_siguiente < 1:
            error_correlativo = "El número inicial debe ser un número entero mayor a 0."
        else:
            numero_candidato = (
                f"{establecimiento.strip() or '001'}-{punto_emision.strip() or '001'}-"
                f"{tipo_documento_codigo.strip() or '01'}-{str(nuevo_siguiente).zfill(8)}"
            )
            ya_existe = db.query(Factura).filter(Factura.numero_documento == numero_candidato).first()
            if ya_existe:
                error_correlativo = (
                    f"No se pudo ajustar el número: ya existe una factura con el número {numero_candidato}. "
                    "Elige otro número inicial."
                )
            else:
                cfg.correlativo_fiscal_actual = nuevo_siguiente - 1

    try:
        cfg.isv_tasa = to_decimal(isv_tasa or 15)
    except (InvalidOperation, ValueError):
        cfg.isv_tasa = Decimal("15")
    cfg.servicios_exentos_default = bool(servicios_exentos_default)
    cfg.prefijo_interno = (prefijo_interno.strip() or "REC").upper()
    cfg.texto_legal_fiscal = texto_legal_fiscal
    cfg.texto_legal_interno = texto_legal_interno
    db.commit()
    if error_correlativo:
        flash(request, error_correlativo, "error")
    else:
        flash(request, "Configuración de facturación guardada correctamente.", "success")
    return RedirectResponse("/configuracion/facturacion", status_code=303)


# ---------------------------------------------------------------------------
# Generar factura a partir de una orden de servicio
# ---------------------------------------------------------------------------
def _validar_fiscal_disponible(cfg: ConfiguracionFacturacion) -> str | None:
    """Devuelve un mensaje de error si la facturación fiscal no está lista
    para emitir, o None si todo está en orden."""
    if not cfg.cai or not cfg.rtn_taller or not cfg.rango_autorizado_inicio or not cfg.rango_autorizado_fin:
        return ("Antes de emitir una factura fiscal debes completar el CAI, tu RTN y el rango autorizado "
                "en Configuración > Facturación (estos datos te los entrega la SAR).")
    if cfg.fecha_limite_emision and date.today() > cfg.fecha_limite_emision:
        return (f"La fecha límite de emisión de tu CAI ({cfg.fecha_limite_emision.strftime('%d/%m/%Y')}) ya venció. "
                "Solicita un nuevo CAI a la SAR y actualízalo en Configuración > Facturación.")
    limite = extraer_correlativo_de_rango(cfg.rango_autorizado_fin)
    siguiente = (cfg.correlativo_fiscal_actual or 0) + 1
    if limite is not None and siguiente > limite:
        return ("Ya se utilizó todo el rango de facturas autorizado por la SAR para este CAI. "
                "Solicita un nuevo CAI y actualízalo en Configuración > Facturación.")
    return None


@router.get("/ordenes/{orden_id}/factura/nueva")
def factura_nueva_form(orden_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        flash(request, "Orden no encontrada.", "error")
        return RedirectResponse("/ordenes", status_code=303)
    cfg = get_or_create_cfg_facturacion(db)
    return templates.TemplateResponse("facturacion/nueva.html", {
        "request": request, "orden": orden, "cfg": cfg, "usuario": usuario,
        "error_fiscal": _validar_fiscal_disponible(cfg),
    })


@router.post("/ordenes/{orden_id}/factura/nueva")
def factura_crear(
    orden_id: int, request: Request,
    tipo: str = Form("interno"), exento: bool = Form(False),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        flash(request, "Orden no encontrada.", "error")
        return RedirectResponse("/ordenes", status_code=303)
    if tipo not in ("interno", "fiscal"):
        tipo = "interno"

    cfg = get_or_create_cfg_facturacion(db)
    cfg_general = _config_general(db)

    if tipo == "fiscal":
        error = _validar_fiscal_disponible(cfg)
        if error:
            flash(request, error, "error")
            return RedirectResponse(f"/ordenes/{orden_id}/factura/nueva", status_code=303)

    total = to_decimal(orden.total)
    tasa = to_decimal(cfg.isv_tasa or 0)
    if exento or tasa <= 0:
        importe_exento, importe_gravado, isv_monto = total, Decimal("0.00"), Decimal("0.00")
    else:
        importe_gravado = (total / (1 + tasa / Decimal(100))).quantize(Decimal("0.01"))
        isv_monto = (total - importe_gravado).quantize(Decimal("0.01"))
        importe_exento = Decimal("0.00")

    numero_documento, correlativo = generar_numero_factura(cfg, tipo)

    factura = Factura(
        orden_id=orden.id,
        tipo=tipo,
        numero_documento=numero_documento,
        correlativo=correlativo,
        cai_usado=cfg.cai if tipo == "fiscal" else None,
        rango_autorizado_inicio=cfg.rango_autorizado_inicio if tipo == "fiscal" else None,
        rango_autorizado_fin=cfg.rango_autorizado_fin if tipo == "fiscal" else None,
        fecha_limite_emision=cfg.fecha_limite_emision if tipo == "fiscal" else None,
        rtn_emisor=cfg.rtn_taller if tipo == "fiscal" else None,
        razon_social_emisor=(cfg.razon_social or cfg.nombre_comercial) if tipo == "fiscal" else None,
        cliente_nombre=orden.cliente.nombre if orden.cliente else "Consumidor final",
        cliente_rtn=(orden.cliente.rtn or "") if orden.cliente else "",
        cliente_direccion=(orden.cliente.direccion or "") if orden.cliente else "",
        fecha_emision=datetime.utcnow(),
        subtotal=total,
        descuento=Decimal("0.00"),
        importe_exento=importe_exento,
        importe_gravado=importe_gravado,
        isv_tasa=tasa,
        isv_monto=isv_monto,
        total=total,
        usuario_nombre=usuario["nombre_completo"],
    )
    db.add(factura)
    db.commit()
    db.refresh(factura)
    flash(request, f"Factura {factura.numero_documento} generada correctamente.", "success")
    return RedirectResponse(f"/facturas/{factura.id}", status_code=303)


# ---------------------------------------------------------------------------
# Listado y detalle
# ---------------------------------------------------------------------------
@router.get("/facturas")
def facturas_list(request: Request, tipo: str = "", db: Session = Depends(get_db), usuario=Depends(login_required)):
    query = db.query(Factura).options(joinedload(Factura.orden))
    if tipo in ("interno", "fiscal"):
        query = query.filter(Factura.tipo == tipo)
    facturas = query.order_by(Factura.id.desc()).all()
    return templates.TemplateResponse("facturacion/list.html", {
        "request": request, "facturas": facturas, "usuario": usuario, "tipo": tipo,
    })


@router.get("/facturas/{factura_id}")
def facturas_detalle(factura_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    factura = db.get(Factura, factura_id)
    if not factura:
        flash(request, "Factura no encontrada.", "error")
        return RedirectResponse("/facturas", status_code=303)
    return templates.TemplateResponse("facturacion/detail.html", {
        "request": request, "factura": factura, "usuario": usuario,
    })


@router.post("/facturas/{factura_id}/anular")
def facturas_anular(
    factura_id: int, request: Request, motivo: str = Form(...),
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    factura = db.get(Factura, factura_id)
    if not factura:
        flash(request, "Factura no encontrada.", "error")
        return RedirectResponse("/facturas", status_code=303)
    if factura.anulada:
        flash(request, "Esta factura ya estaba anulada.", "error")
        return RedirectResponse(f"/facturas/{factura_id}", status_code=303)
    factura.anulada = True
    factura.motivo_anulacion = motivo
    db.commit()
    flash(request, f"Factura {factura.numero_documento} anulada. El número de documento no se reutilizará.", "success")
    return RedirectResponse(f"/facturas/{factura_id}", status_code=303)


@router.post("/facturas/{factura_id}/eliminar")
def facturas_eliminar(
    factura_id: int, request: Request,
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    """Elimina definitivamente un comprobante interno. Las facturas FISCALES
    nunca se pueden eliminar (solo anular): su numeración está sujeta al
    control correlativo de la SAR y borrarla rompería ese control."""
    factura = db.get(Factura, factura_id)
    if not factura:
        flash(request, "Factura no encontrada.", "error")
        return RedirectResponse("/facturas", status_code=303)
    if factura.tipo == "fiscal":
        flash(request, "Las facturas fiscales no se pueden eliminar, solo anular: su numeración está sujeta a control de la SAR.", "error")
        return RedirectResponse(f"/facturas/{factura_id}", status_code=303)
    numero = factura.numero_documento
    db.delete(factura)
    db.commit()
    flash(request, f"Comprobante {numero} eliminado definitivamente.", "success")
    return RedirectResponse("/facturas", status_code=303)


# ---------------------------------------------------------------------------
# PDF: carta y tirilla 80mm
# ---------------------------------------------------------------------------
def _contexto_factura(db: Session, factura_id: int):
    factura = db.get(Factura, factura_id)
    cfg = get_or_create_cfg_facturacion(db)
    cfg_general = _config_general(db)
    return factura, construir_contexto_pdf_factura(factura, cfg, cfg_general)


@router.get("/facturas/{factura_id}/pdf")
def facturas_pdf_ver(factura_id: int, db: Session = Depends(get_db), usuario=Depends(login_required)):
    factura, contexto = _contexto_factura(db, factura_id)
    pdf_bytes = generar_pdf_factura(contexto)
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf",
                              headers={"Content-Disposition": f'inline; filename="{factura.numero_documento}.pdf"'})


@router.get("/facturas/{factura_id}/pdf/descargar")
def facturas_pdf_descargar(factura_id: int, db: Session = Depends(get_db), usuario=Depends(login_required)):
    factura, contexto = _contexto_factura(db, factura_id)
    pdf_bytes = generar_pdf_factura(contexto)
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf",
                              headers={"Content-Disposition": f'attachment; filename="{factura.numero_documento}.pdf"'})


@router.get("/facturas/{factura_id}/pdf/tirilla")
def facturas_tirilla_ver(factura_id: int, db: Session = Depends(get_db), usuario=Depends(login_required)):
    factura, contexto = _contexto_factura(db, factura_id)
    pdf_bytes = generar_ticket_factura(contexto)
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf",
                              headers={"Content-Disposition": f'inline; filename="{factura.numero_documento}_tirilla.pdf"'})


@router.get("/facturas/{factura_id}/pdf/tirilla/descargar")
def facturas_tirilla_descargar(factura_id: int, db: Session = Depends(get_db), usuario=Depends(login_required)):
    factura, contexto = _contexto_factura(db, factura_id)
    pdf_bytes = generar_ticket_factura(contexto)
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf",
                              headers={"Content-Disposition": f'attachment; filename="{factura.numero_documento}_tirilla.pdf"'})
