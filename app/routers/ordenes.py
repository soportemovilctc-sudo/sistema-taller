"""Módulo de órdenes de servicio: creación, edición, estados, abonos y PDF."""
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func
from io import BytesIO

from app.templates_env import templates
from app.database import get_db
from app.models import (
    OrdenServicio, Cliente, Tecnico, HistorialEstado, Pago, Configuracion,
    TIPOS_EQUIPO, ESTADOS_ORDEN, PRIORIDADES, FORMAS_PAGO,
    ACCESORIOS_DISPONIBLES, CONDICIONES_FISICAS, MarcaEquipo, ServicioRapido,
    Producto, OrdenRepuesto, Venta, DetalleVenta, MovimientoInventario, MovimientoFinanciero,
    ConfiguracionFacturacion, Servicio, OrdenServicioExtra,
)
from app.utils.numbering import generar_numero_orden, generar_numero_venta
from app.utils.calculations import calcular_recargo, calcular_total, calcular_saldo, validar_abono, to_decimal, recalcular_orden, aplicar_impuesto
from app.utils.pdf import generar_pdf_orden, construir_contexto_pdf
from app.utils.pdf_ticket import generar_ticket_orden
from app.utils.flash import flash
from app.utils.notificaciones import enviar_whatsapp
from app.deps import login_required, roles_required

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
    vencidas: str = "",
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

    conteo_estados = dict(
        db.query(OrdenServicio.estado, func.count(OrdenServicio.id)).group_by(OrdenServicio.estado).all()
    )
    total_ordenes = db.query(OrdenServicio).count()

    ordenes = query.order_by(OrdenServicio.fecha.desc()).all()
    if vencidas:
        cfg_general = _config(db)
        umbral = cfg_general.dias_vencido_alerta if cfg_general else 3
        ordenes = [
            o for o in ordenes
            if o.estado not in ("ENTREGADO", "CANCELADO") and o.dias_en_taller() >= umbral
        ]
    opciones = _opciones_formulario(db)
    return templates.TemplateResponse("ordenes/list.html", {
        "request": request, "ordenes": ordenes, "usuario": usuario,
        "q": q, "estado": estado, "tecnico_id": tecnico_id, "prioridad": prioridad,
        "vencidas": vencidas,
        "conteo_estados": conteo_estados, "total_ordenes": total_ordenes,
        **opciones,
    })


def _isv_tasa(db: Session) -> Decimal:
    cfg = db.get(ConfiguracionFacturacion, 1)
    if cfg and cfg.isv_tasa is not None:
        return to_decimal(cfg.isv_tasa)
    return to_decimal(15)


def _anotar_precios_con_impuesto(productos, tasa):
    for p in productos:
        p.precio_con_impuesto = aplicar_impuesto(p.precio_venta, tasa)
    return productos


def _servicios_disponibles(db: Session):
    """Servicios activos del catálogo (ver app/routers/servicios.py), para
    el selector de 'Agregar servicio' en el detalle de la orden y al
    generar la factura."""
    return db.query(Servicio).filter(Servicio.activo == True).order_by(Servicio.categoria, Servicio.nombre).all()  # noqa: E712


@router.get("/ordenes/nueva")
def ordenes_nueva_form(request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    cfg = _config(db)
    tasa = _isv_tasa(db)
    # Se muestra todo el inventario activo (no solo lo que tiene existencia
    # en este momento), para poder buscar y ver cualquier repuesto; si se
    # intenta agregar uno sin existencia, la validación de cantidad lo
    # bloquea igual más abajo.
    productos_disponibles = (
        db.query(Producto)
        .filter(Producto.estado == "activo")
        .order_by(Producto.categoria, Producto.nombre)
        .all()
    )
    _anotar_precios_con_impuesto(productos_disponibles, tasa)
    return templates.TemplateResponse("ordenes/form.html", {
        "request": request, "orden": None, "usuario": usuario,
        "recargo_default": cfg.recargo_default_pct if cfg else 0,
        "productos_disponibles": productos_disponibles, "tasa_isv": tasa,
        "servicios_disponibles": _servicios_disponibles(db),
        "hoy_iso": date.today().isoformat(),
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
    mostrar_seguridad_en_pdf: bool = Form(False),
    cotizacion: str = Form("0"),
    recargo_pct: str = Form("0"),
    forma_pago: str = Form("Efectivo"),
    fecha_orden: str = Form(""),
    fecha_entrega: str = Form(""),
    repuesto_producto_id: list[str] = Form([]),
    repuesto_cantidad: list[str] = Form([]),
    repuesto_precio: list[str] = Form([]),
    servicio_nombre: list[str] = Form([]),
    servicio_categoria: list[str] = Form([]),
    servicio_cantidad: list[str] = Form([]),
    servicio_precio: list[str] = Form([]),
    servicio_costo: list[str] = Form([]),
    db: Session = Depends(get_db),
    usuario=Depends(login_required),
):
    # Campos obligatorios además del cliente: marca/modelo del equipo y la
    # condición física al recibir (para dejar constancia del estado y poder
    # identificar el equipo después). El navegador ya bloquea el envío si
    # falta algo, esta es solo una segunda verificación por si acaso.
    faltantes = []
    if not marca.strip():
        faltantes.append("la marca del equipo")
    if not modelo.strip():
        faltantes.append("el modelo del equipo")
    if not condicion:
        faltantes.append("la condición física al recibir")
    if faltantes:
        flash(request, "Antes de crear la orden, completa: " + ", ".join(faltantes) + ".", "error")
        return RedirectResponse("/ordenes/nueva", status_code=303)

    try:
        cot = to_decimal(cotizacion or 0)
        pct = to_decimal(recargo_pct or 0)
        recargo = calcular_recargo(cot, pct)
        total = calcular_total(cot, recargo)
    except ValueError as e:
        flash(request, str(e), "error")
        return RedirectResponse("/ordenes/nueva", status_code=303)

    # Fecha de la orden: por defecto "ahora", pero se puede elegir una fecha
    # pasada (por ejemplo para registrar una orden de ayer que no se alcanzó
    # a cargar el mismo día). No se permite una fecha futura. La hora se
    # toma del momento real en que se guarda, para conservar el orden
    # cronológico entre varias órdenes del mismo día.
    if fecha_orden.strip():
        try:
            fecha_orden_date = datetime.strptime(fecha_orden.strip(), "%Y-%m-%d").date()
        except ValueError:
            flash(request, "La fecha de la orden no es válida.", "error")
            return RedirectResponse("/ordenes/nueva", status_code=303)
        if fecha_orden_date > date.today():
            flash(request, "La fecha de la orden no puede ser una fecha futura.", "error")
            return RedirectResponse("/ordenes/nueva", status_code=303)
    else:
        fecha_orden_date = date.today()
    fecha_dt = datetime.combine(fecha_orden_date, datetime.now().time())

    orden = OrdenServicio(
        numero_orden=generar_numero_orden(db),
        cliente_id=cliente_id,
        tecnico_id=int(tecnico_id) if tecnico_id else None,
        tipo_equipo=tipo_equipo, marca=marca, modelo=modelo, imei=imei, numero_serie=numero_serie,
        accesorios=",".join(accesorios), condicion_fisica=",".join(condicion),
        observaciones_condicion=observaciones_condicion,
        falla_reportada=falla_reportada, diagnostico=diagnostico, trabajo_realizado=trabajo_realizado,
        observaciones=observaciones, prioridad=prioridad, estado=estado,
        pin=pin or None, patron=patron or None, mostrar_seguridad_en_pdf=mostrar_seguridad_en_pdf,
        cotizacion=cot, recargo_pct=pct, recargo_monto=recargo, total=total, abonado=Decimal("0"), saldo=total,
        forma_pago=forma_pago,
        fecha=fecha_dt,
        fecha_entrada=fecha_orden_date,
        fecha_entrega=datetime.strptime(fecha_entrega, "%Y-%m-%d").date() if fecha_entrega else None,
        fecha_cierre=datetime.utcnow() if estado in ("ENTREGADO", "CANCELADO") else None,
    )
    db.add(orden)
    db.flush()

    historial = HistorialEstado(orden_id=orden.id, estado_anterior=None, estado_nuevo=estado,
                                 usuario_nombre=usuario["nombre_completo"], observacion="Orden creada",
                                 fecha=fecha_dt)
    db.add(historial)

    repuestos_agregados = []
    repuestos_con_error = []
    for producto_id_raw, cantidad_raw, precio_raw in zip(repuesto_producto_id, repuesto_cantidad, repuesto_precio or [""] * len(repuesto_producto_id)):
        producto_id_raw = (producto_id_raw or "").strip()
        if not producto_id_raw:
            continue
        try:
            producto_id_val = int(producto_id_raw)
            cantidad_val = int(cantidad_raw)
        except (TypeError, ValueError):
            continue
        if cantidad_val <= 0:
            continue
        producto = db.get(Producto, producto_id_val)
        if not producto:
            continue
        if cantidad_val > producto.existencia:
            repuestos_con_error.append(f"{producto.nombre} (disponible: {producto.existencia})")
            continue
        precio_override = None
        precio_raw = (precio_raw or "").strip()
        if precio_raw:
            precio_val = to_decimal(precio_raw)
            if precio_val > 0:
                precio_override = precio_val.quantize(Decimal("0.01"))
        _agregar_repuesto_a_orden(db, orden, producto, cantidad_val, usuario["nombre_completo"], precio_override)
        repuestos_agregados.append(producto.nombre)

    # Servicios adicionales (opcional): igual que los repuestos, pero cada
    # fila trae su propio nombre/precio/costo en vez de elegirse de un
    # catálogo de productos con existencia. Si el nombre ya existe en el
    # catálogo de Servicios se reutiliza (y se puede ajustar el precio solo
    # para esta orden); si no existe, se crea ahí mismo con el precio y
    # costo escritos, sin tener que ir primero a Servicios.
    servicios_agregados = []
    _cant_servicios = len(servicio_nombre)
    for nombre_raw, cantidad_raw, precio_raw, costo_raw, categoria_raw in zip(
        servicio_nombre,
        servicio_cantidad or [""] * _cant_servicios,
        servicio_precio or [""] * _cant_servicios,
        servicio_costo or [""] * _cant_servicios,
        servicio_categoria or [""] * _cant_servicios,
    ):
        nombre_raw = (nombre_raw or "").strip()
        if not nombre_raw:
            continue
        try:
            cantidad_val = int(cantidad_raw)
        except (TypeError, ValueError):
            cantidad_val = 0
        if cantidad_val <= 0:
            continue
        precio_dec = to_decimal(precio_raw or 0)
        if precio_dec < 0:
            continue
        costo_raw = (costo_raw or "").strip()
        costo_dec = to_decimal(costo_raw) if costo_raw else None
        servicio = db.query(Servicio).filter(Servicio.nombre.ilike(nombre_raw)).first()
        if not servicio:
            servicio = Servicio(
                nombre=nombre_raw, categoria=(categoria_raw or "").strip(),
                precio_venta=precio_dec, costo=costo_dec, activo=True,
            )
            db.add(servicio)
            db.flush()
        _agregar_servicio_a_orden(db, orden, servicio, cantidad_val, usuario["nombre_completo"], precio_override=precio_dec)
        servicios_agregados.append(servicio.nombre)

    if repuestos_agregados or servicios_agregados:
        db.flush()
        db.refresh(orden)
        recalcular_orden(orden)

    db.commit()

    if repuestos_con_error:
        flash(request, "No se pudieron agregar estos repuestos por falta de existencia: " + ", ".join(repuestos_con_error), "error")
    mensaje = f"Orden {orden.numero_orden} creada correctamente."
    if repuestos_agregados:
        mensaje += f" Repuestos agregados: {', '.join(repuestos_agregados)}."
    if servicios_agregados:
        mensaje += f" Servicios agregados: {', '.join(servicios_agregados)}."
    flash(request, mensaje, "success")
    return RedirectResponse(f"/ordenes/{orden.id}", status_code=303)


@router.get("/ordenes/{orden_id}")
def ordenes_detalle(orden_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        flash(request, "Orden no encontrada.", "error")
        return RedirectResponse("/ordenes", status_code=303)
    opciones = _opciones_formulario(db)
    tasa = _isv_tasa(db)
    # Igual que en "Nueva orden": se muestra todo el inventario activo, no
    # solo lo que tiene existencia ahora mismo.
    productos_disponibles = (
        db.query(Producto)
        .filter(Producto.estado == "activo")
        .order_by(Producto.categoria, Producto.nombre)
        .all()
    )
    _anotar_precios_con_impuesto(productos_disponibles, tasa)
    return templates.TemplateResponse("ordenes/detail.html", {
        "request": request, "orden": orden, "usuario": usuario,
        "productos_disponibles": productos_disponibles, "tasa_isv": tasa,
        "servicios_disponibles": _servicios_disponibles(db), **opciones,
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
        "hoy_iso": date.today().isoformat(),
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
    mostrar_seguridad_en_pdf: bool = Form(False),
    cotizacion: str = Form("0"),
    recargo_pct: str = Form("0"),
    forma_pago: str = Form("Efectivo"),
    fecha_orden: str = Form(""),
    fecha_entrega: str = Form(""),
    db: Session = Depends(get_db),
    usuario=Depends(login_required),
):
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        return RedirectResponse("/ordenes", status_code=303)

    faltantes = []
    if not marca.strip():
        faltantes.append("la marca del equipo")
    if not modelo.strip():
        faltantes.append("el modelo del equipo")
    if not condicion:
        faltantes.append("la condición física al recibir")
    if faltantes:
        flash(request, "Antes de guardar, completa: " + ", ".join(faltantes) + ".", "error")
        return RedirectResponse(f"/ordenes/{orden_id}/editar", status_code=303)

    # Fecha de la orden: se puede corregir a una fecha pasada (por ejemplo si
    # se cargó tarde una orden de ayer). Se conserva la hora que ya tenía la
    # orden para no alterar su posición cronológica entre otras del mismo día.
    if fecha_orden.strip():
        try:
            fecha_orden_date = datetime.strptime(fecha_orden.strip(), "%Y-%m-%d").date()
        except ValueError:
            flash(request, "La fecha de la orden no es válida.", "error")
            return RedirectResponse(f"/ordenes/{orden_id}/editar", status_code=303)
        if fecha_orden_date > date.today():
            flash(request, "La fecha de la orden no puede ser una fecha futura.", "error")
            return RedirectResponse(f"/ordenes/{orden_id}/editar", status_code=303)
        hora_actual = orden.fecha.time() if orden.fecha else datetime.now().time()
        orden.fecha = datetime.combine(fecha_orden_date, hora_actual)
        orden.fecha_entrada = fecha_orden_date

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
    orden.mostrar_seguridad_en_pdf = mostrar_seguridad_en_pdf
    orden.forma_pago = forma_pago
    orden.fecha_entrega = datetime.strptime(fecha_entrega, "%Y-%m-%d").date() if fecha_entrega else None

    recalcular_orden(orden)
    db.commit()
    flash(request, "Orden actualizada correctamente.", "success")
    return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)


def _aplicar_cambio_estado(db: Session, orden: OrdenServicio, nuevo_estado: str, observacion: str, usuario_nombre: str):
    """Aplica un cambio de estado a una orden (incluye el pago automático al
    marcar ENTREGADO). No hace commit ni valida que nuevo_estado sea válido;
    eso lo decide quien llama. Devuelve el monto del pago automático
    registrado, o None si no aplicó."""
    estado_anterior = orden.estado
    historial = HistorialEstado(
        orden_id=orden.id, estado_anterior=estado_anterior, estado_nuevo=nuevo_estado,
        usuario_nombre=usuario_nombre, observacion=observacion,
    )
    orden.estado = nuevo_estado
    if nuevo_estado in ("ENTREGADO", "CANCELADO"):
        if not orden.fecha_cierre:
            orden.fecha_cierre = datetime.utcnow()
    else:
        orden.fecha_cierre = None
    # Si la orden vuelve a entrar a LISTO PARA ENTREGAR (por ejemplo se
    # corrigió algo después de haber avisado al cliente), se reinicia el
    # aviso para que quede pendiente avisar de nuevo. Antes de dejarlo
    # pendiente, intenta avisarle automáticamente por WhatsApp (si hay
    # credenciales de Twilio configuradas en Configuración >
    # Notificaciones); si no hay credenciales o el envío falla, se queda
    # pendiente igual que antes y el botón manual de "Avisar por WhatsApp"
    # sigue disponible como respaldo.
    if nuevo_estado == "LISTO PARA ENTREGAR" and estado_anterior != "LISTO PARA ENTREGAR":
        orden.notificado_listo = False
        orden.fecha_notificado_listo = None
        cfg = db.get(Configuracion, 1)
        cliente = orden.cliente
        telefono_cliente = (cliente.whatsapp or cliente.telefono or "") if cliente else ""
        if telefono_cliente:
            mensaje = (
                f"Hola {cliente.nombre if cliente else ''}, tu equipo (orden {orden.numero_orden}) "
                f"ya está listo para entregar."
            )
            if orden.saldo and orden.saldo > 0:
                mensaje += f" Saldo pendiente: L{orden.saldo}."
            mensaje += " ¡Te esperamos!"
            if enviar_whatsapp(cfg, telefono_cliente, mensaje):
                orden.notificado_listo = True
                orden.fecha_notificado_listo = datetime.utcnow()
    db.add(historial)

    # Al marcar la orden como ENTREGADO se asume que ya se cobró todo:
    # un técnico no debería entregar el equipo sin que el cliente haya
    # pagado el saldo. Si queda saldo pendiente en ese momento, se
    # registra automáticamente un abono por ese monto (en vez de
    # obligar a un paso aparte de "Registrar abono" antes de poder
    # cerrar la orden).
    monto_pago_automatico = None
    if nuevo_estado == "ENTREGADO" and orden.saldo and orden.saldo > 0:
        monto_pago_automatico = orden.saldo
        db.add(Pago(
            orden_id=orden.id, monto=monto_pago_automatico, forma_pago=orden.forma_pago or "Efectivo",
            usuario_nombre=usuario_nombre,
            observacion="Pago automático al marcar la orden como ENTREGADO",
        ))
        # Se registra también como ingreso en Reportes (antes solo quedaba
        # en el historial de pagos de la orden, invisible ahí).
        db.add(MovimientoFinanciero(
            tipo="ingreso", categoria="Cancelación de orden (automático)", monto=monto_pago_automatico,
            descripcion=f"Pago automático al entregar - Orden {orden.numero_orden}",
            usuario_nombre=usuario_nombre, referencia=orden.numero_orden,
        ))
        db.flush()
        db.refresh(orden)
        recalcular_orden(orden)
    return monto_pago_automatico


def _aplicar_abono(db: Session, orden: OrdenServicio, monto, forma_pago: str, observacion: str, usuario_nombre: str) -> Decimal:
    """Registra un abono sobre una orden (valida el monto contra el saldo
    actual, puede lanzar ValueError/InvalidOperation). No hace commit.
    Devuelve el monto ya validado."""
    monto_validado = validar_abono(monto, orden.saldo)
    pago = Pago(orden_id=orden.id, monto=monto_validado, forma_pago=forma_pago,
                usuario_nombre=usuario_nombre, observacion=observacion)
    db.add(pago)
    # Se registra también como ingreso en Reportes (antes solo quedaba en
    # el historial de pagos de la orden, invisible ahí).
    db.add(MovimientoFinanciero(
        tipo="ingreso", categoria="Abono de orden", monto=monto_validado,
        descripcion=f"Abono - Orden {orden.numero_orden}" + (f" ({observacion})" if observacion else ""),
        usuario_nombre=usuario_nombre, referencia=orden.numero_orden,
    ))
    db.flush()
    db.refresh(orden)
    recalcular_orden(orden)
    return monto_validado


@router.post("/ordenes/{orden_id}/estado")
def ordenes_cambiar_estado(
    orden_id: int, request: Request,
    nuevo_estado: str = Form(...), observacion: str = Form(""), redirect_to: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    orden = db.get(OrdenServicio, orden_id)
    if orden and nuevo_estado in ESTADOS_ORDEN:
        monto_pago_automatico = _aplicar_cambio_estado(db, orden, nuevo_estado, observacion, usuario["nombre_completo"])
        db.commit()
        if monto_pago_automatico:
            flash(request, f"Estado actualizado a ENTREGADO. Se registró un pago automático de {monto_pago_automatico} para saldar la orden.", "success")
        else:
            flash(request, f"Estado actualizado a {nuevo_estado}.", "success")
    destino = redirect_to if redirect_to.startswith("/") else f"/ordenes/{orden_id}"
    return RedirectResponse(destino, status_code=303)


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
        monto_validado = _aplicar_abono(db, orden, monto, forma_pago, observacion, usuario["nombre_completo"])
    except (ValueError, InvalidOperation) as e:
        flash(request, str(e), "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    db.commit()
    flash(request, f"Abono de {monto_validado} registrado correctamente.", "success")
    return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)


def _agregar_repuesto_a_orden(db: Session, orden: OrdenServicio, producto: Producto, cantidad: int, usuario_nombre: str, precio_override: Optional[Decimal] = None) -> OrdenRepuesto:
    """Descuenta `cantidad` unidades de `producto` y las agrega a `orden`:
    crea la Venta/DetalleVenta (igual que en POS, enlazada a la orden),
    el MovimientoInventario de salida, el MovimientoFinanciero de ingreso
    y el registro OrdenRepuesto. No valida existencia disponible (el
    llamador debe validarla antes) ni hace commit ni recalcula la orden.
    Si se pasa `precio_override`, se usa ese precio unitario en vez del
    precio de venta del producto (para permitir ajustar el precio al
    agregar el repuesto a la orden). Si no se pasa, el precio por defecto
    es el precio de venta del producto CON el impuesto (ISV) incluido,
    porque el total de la orden/factura se trata como un monto que ya
    incluye impuesto (ver facturación)."""
    precio = precio_override if precio_override is not None else aplicar_impuesto(producto.precio_venta, _isv_tasa(db))
    subtotal = (precio * cantidad).quantize(Decimal("0.01"))

    venta = Venta(
        numero_venta=generar_numero_venta(db), cliente_id=orden.cliente_id, orden_id=orden.id,
        subtotal=subtotal, descuento=Decimal("0.00"), total=subtotal,
        forma_pago=orden.forma_pago or "Efectivo", monto_recibido=subtotal, cambio=Decimal("0.00"),
        usuario_nombre=usuario_nombre,
    )
    db.add(venta)
    db.flush()

    db.add(DetalleVenta(venta_id=venta.id, producto_id=producto.id, cantidad=cantidad,
                         precio_unitario=precio, subtotal=subtotal))

    producto.existencia -= cantidad
    db.add(MovimientoInventario(
        producto_id=producto.id, tipo="salida", cantidad=cantidad,
        existencia_resultante=producto.existencia, usuario_nombre=usuario_nombre,
        motivo=f"Orden {orden.numero_orden}",
    ))

    db.add(MovimientoFinanciero(
        tipo="ingreso", categoria="Venta de repuesto (orden)", monto=subtotal,
        descripcion=f"{producto.nombre} x{cantidad} - Orden {orden.numero_orden}",
        usuario_nombre=usuario_nombre, referencia=orden.numero_orden,
    ))

    orden_repuesto = OrdenRepuesto(
        orden_id=orden.id, producto_id=producto.id, venta_id=venta.id,
        cantidad=cantidad, precio_unitario=precio, subtotal=subtotal,
        usuario_nombre=usuario_nombre,
    )
    db.add(orden_repuesto)
    return orden_repuesto


def _agregar_servicio_a_orden(db: Session, orden: OrdenServicio, servicio: Servicio, cantidad: int, usuario_nombre: str, precio_override: Optional[Decimal] = None) -> OrdenServicioExtra:
    """Agrega un servicio del catálogo (ver app/routers/servicios.py) a la
    orden: registra el ingreso en Reportes/Contabilidad y guarda una copia
    del precio y costo del servicio al momento de agregarlo (igual que con
    los repuestos), para que un cambio posterior en el catálogo no altere
    órdenes o facturas ya emitidas. No hace commit ni recalcula la orden;
    quien llama decide cuándo hacerlo. Si se pasa `precio_override`, se usa
    ese precio en vez del precio de venta del catálogo. A diferencia de los
    repuestos, el precio del servicio NO lleva el ajuste de impuesto (se
    trata igual que la cotización: un monto final que ya cobra el taller)."""
    precio = precio_override if precio_override is not None else to_decimal(servicio.precio_venta)
    subtotal = (precio * cantidad).quantize(Decimal("0.01"))
    costo_unitario = to_decimal(servicio.costo) if servicio.costo is not None else None

    db.add(MovimientoFinanciero(
        tipo="ingreso", categoria="Venta de servicio (orden)", monto=subtotal,
        descripcion=f"{servicio.nombre} x{cantidad} - Orden {orden.numero_orden}",
        usuario_nombre=usuario_nombre, referencia=orden.numero_orden,
    ))

    orden_servicio_extra = OrdenServicioExtra(
        orden_id=orden.id, servicio_id=servicio.id, cantidad=cantidad,
        precio_unitario=precio, costo_unitario=costo_unitario, subtotal=subtotal,
        usuario_nombre=usuario_nombre,
    )
    db.add(orden_servicio_extra)
    return orden_servicio_extra


@router.post("/ordenes/{orden_id}/repuestos")
def ordenes_agregar_repuesto(
    orden_id: int, request: Request,
    producto_id: int = Form(...), cantidad: str = Form("1"), precio: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    """Descuenta un repuesto del inventario y lo agrega a la orden: baja la
    existencia del producto, queda registrado como venta (para reportes y
    contabilidad) y su costo se suma al total de la orden y a la factura
    que se genere a partir de ella."""
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        return RedirectResponse("/ordenes", status_code=303)

    producto = db.get(Producto, producto_id)
    if not producto:
        flash(request, "Producto no encontrado.", "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    try:
        cantidad_int = int(cantidad)
    except (TypeError, ValueError):
        cantidad_int = 0
    if cantidad_int <= 0:
        flash(request, "La cantidad debe ser mayor a cero.", "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)
    if cantidad_int > producto.existencia:
        flash(request, f"No hay suficiente existencia de '{producto.nombre}' (disponible: {producto.existencia}).", "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    precio_override = None
    precio_raw = (precio or "").strip()
    if precio_raw:
        precio_val = to_decimal(precio_raw)
        if precio_val > 0:
            precio_override = precio_val.quantize(Decimal("0.01"))

    _agregar_repuesto_a_orden(db, orden, producto, cantidad_int, usuario["nombre_completo"], precio_override)
    db.flush()
    db.refresh(orden)
    recalcular_orden(orden)
    db.commit()
    flash(request, f"Repuesto '{producto.nombre}' agregado a la orden y descontado del inventario.", "success")
    return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)


@router.post("/ordenes/{orden_id}/repuestos/{orden_repuesto_id}/eliminar")
def ordenes_quitar_repuesto(
    orden_id: int, orden_repuesto_id: int, request: Request,
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    """Deshace el agregado de un repuesto a la orden (por ejemplo si se
    agregó por error o con la cantidad equivocada): repone la existencia
    en el inventario dejando su propio movimiento de entrada (para que
    quede registrado el porqué, sin borrar el movimiento de salida
    original), revierte el ingreso contable con un movimiento de gasto de
    corrección, y elimina la venta/detalle asociados (esa venta se creó
    únicamente para representar este repuesto dentro de la orden; no es
    una venta independiente del POS). No se permite si la orden ya tiene
    una factura vigente (fiscal o interna, no anulada): su total ya quedó
    impreso y no se actualiza solo."""
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        flash(request, "Orden no encontrada.", "error")
        return RedirectResponse("/ordenes", status_code=303)

    orden_repuesto = db.get(OrdenRepuesto, orden_repuesto_id)
    if not orden_repuesto or orden_repuesto.orden_id != orden.id:
        flash(request, "Ese repuesto no pertenece a esta orden.", "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    if any(not f.anulada for f in orden.facturas):
        flash(request, "No se puede quitar un repuesto: esta orden ya tiene una factura vigente. Anúlala primero (un administrador puede hacerlo) antes de modificar los repuestos.", "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    producto = orden_repuesto.producto
    cantidad = orden_repuesto.cantidad
    subtotal = orden_repuesto.subtotal
    nombre_producto = producto.nombre if producto else "(producto ya no existe)"

    if producto:
        producto.existencia += cantidad
        db.add(MovimientoInventario(
            producto_id=producto.id, tipo="entrada", cantidad=cantidad,
            existencia_resultante=producto.existencia, usuario_nombre=usuario["nombre_completo"],
            motivo=f"Se quitó de la Orden {orden.numero_orden} (repuesto agregado por error)",
        ))

    db.add(MovimientoFinanciero(
        tipo="gasto", categoria="Corrección de repuesto (orden)", monto=subtotal,
        descripcion=f"Se quitó {nombre_producto} x{cantidad} de la Orden {orden.numero_orden}",
        usuario_nombre=usuario["nombre_completo"], referencia=orden.numero_orden,
    ))

    venta = orden_repuesto.venta
    db.delete(orden_repuesto)
    if venta:
        db.delete(venta)  # cascada: sus DetalleVenta (cascade="all,delete-orphan")

    db.flush()
    db.refresh(orden)
    recalcular_orden(orden)
    db.commit()
    flash(request, f"Se quitó '{nombre_producto}' de la orden y se repuso al inventario.", "success")
    return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)


@router.post("/ordenes/{orden_id}/servicios")
def ordenes_agregar_servicio(
    orden_id: int, request: Request,
    nombre: str = Form(...), categoria: str = Form(""), cantidad: str = Form("1"),
    precio_venta: str = Form("0"), costo: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    """Agrega un servicio a la orden por nombre, sin pasos extra: si ya
    existe un servicio con ese nombre en el catálogo (ver Servicio) se
    reutiliza ese (se puede ajustar el precio solo para esta orden); si no
    existe, se crea en el catálogo con el precio y costo escritos aquí, sin
    tener que ir primero a Servicios y luego volver. Queda registrado como
    ingreso (para reportes y contabilidad) y su precio se suma al total de
    la orden y a la factura que se genere a partir de ella."""
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        return RedirectResponse("/ordenes", status_code=303)

    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        flash(request, "Escribe un nombre para el servicio.", "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    try:
        cantidad_int = int(cantidad)
    except (TypeError, ValueError):
        cantidad_int = 0
    if cantidad_int <= 0:
        flash(request, "La cantidad debe ser mayor a cero.", "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    precio_dec = to_decimal(precio_venta or 0)
    if precio_dec < 0:
        flash(request, "El precio de venta no puede ser negativo.", "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    costo_raw = (costo or "").strip()
    costo_dec = None
    if costo_raw:
        costo_dec = to_decimal(costo_raw)
        if costo_dec < 0:
            flash(request, "El costo no puede ser negativo.", "error")
            return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    servicio = db.query(Servicio).filter(Servicio.nombre.ilike(nombre_limpio)).first()
    mensaje_catalogo = ""
    if not servicio:
        servicio = Servicio(
            nombre=nombre_limpio, categoria=categoria.strip(),
            precio_venta=precio_dec, costo=costo_dec, activo=True,
        )
        db.add(servicio)
        db.flush()
        mensaje_catalogo = " y se guardó en el catálogo de Servicios para la próxima vez"

    _agregar_servicio_a_orden(db, orden, servicio, cantidad_int, usuario["nombre_completo"], precio_override=precio_dec)
    db.flush()
    db.refresh(orden)
    recalcular_orden(orden)
    db.commit()
    flash(request, f"Servicio '{servicio.nombre}' agregado a la orden{mensaje_catalogo}.", "success")
    return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)


@router.post("/ordenes/{orden_id}/servicios/{item_id}/eliminar")
def ordenes_quitar_servicio(
    orden_id: int, item_id: int, request: Request,
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    """Deshace el agregado de un servicio a la orden (por ejemplo si se
    agregó por error): revierte el ingreso contable con un movimiento de
    gasto de corrección, igual que al quitar un repuesto. No se permite si
    la orden ya tiene una factura vigente (fiscal o interna, no anulada):
    su total ya quedó impreso y no se actualiza solo."""
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        flash(request, "Orden no encontrada.", "error")
        return RedirectResponse("/ordenes", status_code=303)

    item = db.get(OrdenServicioExtra, item_id)
    if not item or item.orden_id != orden.id:
        flash(request, "Ese servicio no pertenece a esta orden.", "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    if any(not f.anulada for f in orden.facturas):
        flash(request, "No se puede quitar un servicio: esta orden ya tiene una factura vigente. Anúlala primero (un administrador puede hacerlo) antes de modificar los servicios.", "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    nombre_servicio = item.servicio.nombre if item.servicio else "(servicio ya no existe)"
    cantidad = item.cantidad
    subtotal = item.subtotal

    db.add(MovimientoFinanciero(
        tipo="gasto", categoria="Corrección de servicio (orden)", monto=subtotal,
        descripcion=f"Se quitó {nombre_servicio} x{cantidad} de la Orden {orden.numero_orden}",
        usuario_nombre=usuario["nombre_completo"], referencia=orden.numero_orden,
    ))

    db.delete(item)
    db.flush()
    db.refresh(orden)
    recalcular_orden(orden)
    db.commit()
    flash(request, f"Se quitó '{nombre_servicio}' de la orden.", "success")
    return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)


@router.post("/ordenes/{orden_id}/eliminar")
def ordenes_eliminar(
    orden_id: int, request: Request,
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    """Elimina definitivamente una orden de servicio (solo administradores).
    No se permite si la orden tiene una factura FISCAL asociada (esas
    facturas no se pueden eliminar, solo anular, por control de la SAR).
    Las facturas internas generadas desde la orden se eliminan junto con
    ella. Las ventas de repuestos que se hayan generado desde la orden NO
    se eliminan (para no perder el historial real de inventario y
    contabilidad ya consumido); solo quedan desvinculadas de la orden."""
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        flash(request, "Orden no encontrada.", "error")
        return RedirectResponse("/ordenes", status_code=303)

    if any(f.tipo == "fiscal" for f in orden.facturas):
        flash(request, "No se puede eliminar esta orden: tiene una factura fiscal asociada (las facturas fiscales no se pueden eliminar, solo anular).", "error")
        return RedirectResponse(f"/ordenes/{orden_id}", status_code=303)

    numero_orden = orden.numero_orden
    for f in list(orden.facturas):
        db.delete(f)
    db.query(Venta).filter(Venta.orden_id == orden.id).update({"orden_id": None})
    db.flush()
    db.delete(orden)  # cascada: historial de estados, abonos y repuestos de la orden
    db.commit()
    flash(request, f"Orden {numero_orden} eliminada definitivamente.", "success")
    return RedirectResponse("/ordenes", status_code=303)


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
    se debe adjuntar manualmente, WhatsApp Web no permite adjuntar por enlace).
    Si la orden está LISTO PARA ENTREGAR, usar este botón cuenta como avisar
    al cliente: se marca como notificada para que no quede pendiente."""
    orden = db.get(OrdenServicio, orden_id)
    mensaje = (
        f"Hola {orden.cliente.nombre if orden.cliente else ''}, aquí está el resumen de tu orden "
        f"{orden.numero_orden}: Estado {orden.estado}, Total L{orden.total}, Saldo pendiente L{orden.saldo}."
    )
    telefono = (orden.cliente.whatsapp or orden.cliente.telefono or "") if orden.cliente else ""
    telefono_limpio = "".join(ch for ch in telefono if ch.isdigit())
    if orden.estado == "LISTO PARA ENTREGAR" and not orden.notificado_listo:
        orden.notificado_listo = True
        orden.fecha_notificado_listo = datetime.utcnow()
        db.commit()
    import urllib.parse
    link = f"https://wa.me/{telefono_limpio}?text={urllib.parse.quote(mensaje)}"
    return RedirectResponse(link, status_code=303)


@router.post("/ordenes/{orden_id}/marcar-avisado")
def ordenes_marcar_avisado(orden_id: int, request: Request, redirect_to: str = Form(""),
                            db: Session = Depends(get_db), usuario=Depends(login_required)):
    """Marca manualmente que ya se avisó al cliente de que el equipo está
    listo (por ejemplo, si se le llamó por teléfono en vez de usar el botón
    de WhatsApp)."""
    orden = db.get(OrdenServicio, orden_id)
    if orden:
        orden.notificado_listo = True
        orden.fecha_notificado_listo = datetime.utcnow()
        db.commit()
        flash(request, "Se marcó al cliente como avisado.", "success")
    destino = redirect_to if redirect_to.startswith("/") else f"/ordenes/{orden_id}"
    return RedirectResponse(destino, status_code=303)
