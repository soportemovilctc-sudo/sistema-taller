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
from app.models import (
    Factura, ConfiguracionFacturacion, Configuracion, OrdenServicio, Tecnico, Producto, Servicio,
    MovimientoFinanciero, CATEGORIA_VENTA_FACTURADA,
)
from app.deps import login_required, roles_required
from app.utils.flash import flash
from app.utils.calculations import to_decimal, aplicar_impuesto, recalcular_orden
from app.utils.numbering import generar_numero_factura, extraer_correlativo_de_rango
from app.utils.pdf import generar_pdf_factura, construir_contexto_pdf_factura
from app.utils.pdf_ticket import generar_ticket_factura
from app.utils.libro_diario import registrar_asiento_para_movimiento, eliminar_asiento_de_movimiento
# Se reutilizan las mismas funciones que ya usan "Repuestos utilizados" y
# "Servicios agregados" al editar una orden, para no duplicar la lógica de
# descontar inventario y registrar la venta (ver ordenes.py). Ya no generan
# el ingreso financiero: ese se genera aquí mismo, una sola vez, al emitir
# la factura (ver CATEGORIA_VENTA_FACTURADA).
from app.routers.ordenes import _agregar_repuesto_a_orden, _agregar_servicio_a_orden, _servicios_disponibles

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
    tecnicos = db.query(Tecnico).filter(Tecnico.activo == True).order_by(Tecnico.nombre).all()  # noqa: E712

    # Repuestos disponibles para poder agregar aquí mismo, al generar la
    # factura, el que se haya usado en la reparación (opcional: no todos
    # los equipos llevan un repuesto, algunos solo pasan por diagnóstico).
    tasa_isv = to_decimal(cfg.isv_tasa if cfg.isv_tasa is not None else 15)
    # Se muestra todo el inventario activo (no solo lo que tiene existencia
    # ahora mismo), igual que en "Nueva orden" y el detalle de la orden.
    productos_disponibles = (
        db.query(Producto)
        .filter(Producto.estado == "activo")
        .order_by(Producto.categoria, Producto.nombre)
        .all()
    )
    for p in productos_disponibles:
        p.precio_con_impuesto = aplicar_impuesto(p.precio_venta, tasa_isv)

    return templates.TemplateResponse("facturacion/nueva.html", {
        "request": request, "orden": orden, "cfg": cfg, "usuario": usuario,
        "error_fiscal": _validar_fiscal_disponible(cfg),
        "tecnicos": tecnicos,
        "productos_disponibles": productos_disponibles, "tasa_isv": tasa_isv,
        "servicios_disponibles": _servicios_disponibles(db),
    })


@router.post("/ordenes/{orden_id}/factura/nueva")
def factura_crear(
    orden_id: int, request: Request,
    tipo: str = Form("interno"), exento: bool = Form(False), tecnico_reparacion_id: str = Form(""),
    repuesto_producto_id: str = Form(""), repuesto_cantidad: str = Form("1"), repuesto_precio: str = Form(""),
    servicio_nombre: str = Form(""), servicio_categoria: str = Form(""),
    servicio_cantidad: str = Form("1"), servicio_precio: str = Form(""), servicio_costo: str = Form(""),
    cliente_rtn: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        flash(request, "Orden no encontrada.", "error")
        return RedirectResponse("/ordenes", status_code=303)
    if tipo not in ("interno", "fiscal"):
        tipo = "interno"

    # El técnico que RECIBIÓ el equipo (orden.tecnico_id) no siempre es
    # quien hizo la reparación, así que se guarda aparte y se puede
    # corregir aquí mismo al momento de facturar.
    orden.tecnico_reparacion_id = int(tecnico_reparacion_id) if tecnico_reparacion_id else None

    # Repuesto usado (opcional): si el equipo llevó un repuesto y todavía
    # no se había registrado en la orden, se agrega aquí mismo antes de
    # calcular el total de la factura (algunos equipos solo se dejan para
    # diagnóstico y no llevan repuesto, por eso este campo no es obligatorio).
    producto_id_raw = (repuesto_producto_id or "").strip()
    if producto_id_raw:
        try:
            producto_id_val = int(producto_id_raw)
        except (TypeError, ValueError):
            producto_id_val = None
        try:
            cantidad_val = int(repuesto_cantidad or "1")
        except (TypeError, ValueError):
            cantidad_val = 0

        if not producto_id_val or cantidad_val <= 0:
            flash(request, "Cantidad inválida para el repuesto seleccionado.", "error")
            return RedirectResponse(f"/ordenes/{orden_id}/factura/nueva", status_code=303)

        producto = db.get(Producto, producto_id_val)
        if not producto:
            flash(request, "El repuesto seleccionado no existe.", "error")
            return RedirectResponse(f"/ordenes/{orden_id}/factura/nueva", status_code=303)
        if cantidad_val > producto.existencia:
            flash(request, f"No hay suficiente existencia de '{producto.nombre}' (disponible: {producto.existencia}).", "error")
            return RedirectResponse(f"/ordenes/{orden_id}/factura/nueva", status_code=303)

        precio_override = None
        precio_raw = (repuesto_precio or "").strip()
        if precio_raw:
            precio_val = to_decimal(precio_raw)
            if precio_val > 0:
                precio_override = precio_val.quantize(Decimal("0.01"))

        _agregar_repuesto_a_orden(db, orden, producto, cantidad_val, usuario["nombre_completo"], precio_override)
        db.flush()
        db.refresh(orden)
        recalcular_orden(orden)
        db.flush()

    # Servicio adicional (opcional): igual que el repuesto de arriba, por si
    # el trabajo llevó un servicio que todavía no se había registrado en la
    # orden. Se busca por nombre en el catálogo (ver Servicio); si no existe
    # todavía, se crea ahí mismo con el precio (y costo, si se escribió).
    servicio_nombre_raw = (servicio_nombre or "").strip()
    if servicio_nombre_raw:
        try:
            servicio_cantidad_val = int(servicio_cantidad or "1")
        except (TypeError, ValueError):
            servicio_cantidad_val = 0
        if servicio_cantidad_val <= 0:
            flash(request, "Cantidad inválida para el servicio.", "error")
            return RedirectResponse(f"/ordenes/{orden_id}/factura/nueva", status_code=303)

        servicio_precio_raw = (servicio_precio or "").strip()
        servicio_precio_dec = to_decimal(servicio_precio_raw) if servicio_precio_raw else to_decimal(0)
        servicio_costo_raw = (servicio_costo or "").strip()
        servicio_costo_dec = to_decimal(servicio_costo_raw) if servicio_costo_raw else None

        servicio = db.query(Servicio).filter(Servicio.nombre.ilike(servicio_nombre_raw)).first()
        if not servicio:
            servicio = Servicio(
                nombre=servicio_nombre_raw, categoria=(servicio_categoria or "").strip(),
                precio_venta=servicio_precio_dec, costo=servicio_costo_dec, activo=True,
            )
            db.add(servicio)
            db.flush()

        _agregar_servicio_a_orden(db, orden, servicio, servicio_cantidad_val, usuario["nombre_completo"], servicio_precio_dec)
        db.flush()
        db.refresh(orden)
        recalcular_orden(orden)
        db.flush()

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

    # El RTN se puede escribir o corregir aquí mismo al momento de facturar
    # (antes solo se podía editar yendo al registro del Cliente aparte). Si
    # la orden tiene cliente, se guarda también en su ficha para que quede
    # disponible la próxima vez que se le facture.
    cliente_rtn_final = (cliente_rtn or "").strip()
    if orden.cliente and cliente_rtn_final != (orden.cliente.rtn or ""):
        orden.cliente.rtn = cliente_rtn_final

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
        cliente_rtn=cliente_rtn_final,
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
    db.flush()
    db.refresh(factura)

    # Único momento en que una orden genera un ingreso contable: antes se
    # generaba (y se contaba dos veces) al agregar el repuesto/servicio y
    # otra vez al cobrarlo; ahora solo se genera aquí, al emitir la
    # factura (ver CATEGORIA_VENTA_FACTURADA).
    mov = MovimientoFinanciero(
        tipo="ingreso", categoria=CATEGORIA_VENTA_FACTURADA, monto=factura.total,
        descripcion=f"Factura {factura.numero_documento} - Orden {orden.numero_orden}",
        usuario_nombre=usuario["nombre_completo"], referencia=orden.numero_orden,
        fecha=factura.fecha_emision, factura_id=factura.id,
    )
    db.add(mov)
    db.flush()
    registrar_asiento_para_movimiento(db, mov, monto_neto=(total - isv_monto), isv_monto=isv_monto)

    db.commit()
    db.refresh(factura)
    flash(request, f"Factura {factura.numero_documento} generada correctamente.", "success")
    return RedirectResponse(f"/facturas/{factura.id}", status_code=303)


# ---------------------------------------------------------------------------
# Listado y detalle
# ---------------------------------------------------------------------------
@router.get("/facturas")
def facturas_list(request: Request, tipo: str = "", db: Session = Depends(get_db), usuario=Depends(login_required)):
    query = db.query(Factura).options(joinedload(Factura.orden), joinedload(Factura.venta))
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

    # El ingreso contable que generó esta factura (ver CATEGORIA_VENTA_
    # FACTURADA) ya no debe contar: se excluye (nunca se borra) igual que
    # cualquier otro movimiento que deja de ser válido.
    mov = db.query(MovimientoFinanciero).filter(MovimientoFinanciero.factura_id == factura.id).first()
    if mov:
        mov.excluir_de_contabilidad = True
        eliminar_asiento_de_movimiento(db, mov.id)

    db.commit()
    flash(request, f"Factura {factura.numero_documento} anulada. El número de documento no se reutilizará.", "success")
    return RedirectResponse(f"/facturas/{factura_id}", status_code=303)


# NOTA: facturas_eliminar() se removió a propósito. Eliminar definitivamente
# una factura dejaba huérfanos los movimientos de Caja/Inventario que la orden
# o venta asociada ya había generado (sin relación/FK para poder limpiarlos
# automáticamente). De ahora en adelante las facturas (internas y fiscales)
# solo se pueden anular, nunca eliminar.


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
