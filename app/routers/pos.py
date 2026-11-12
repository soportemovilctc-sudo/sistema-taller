"""Punto de venta (POS): carrito, cálculo de totales, cobro y descuento de inventario."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.templates_env import templates
from app.database import get_db
from app.models import (
    Producto, Venta, DetalleVenta, MovimientoInventario, MovimientoFinanciero, Cliente,
    ConfiguracionFacturacion, Factura, Cotizacion, COTIZACION_VIGENTE, COTIZACION_ACEPTADA,
)
from app.schemas import VentaIn
from app.utils.numbering import generar_numero_venta, generar_numero_factura
from app.utils.calculations import to_decimal, aplicar_impuesto
from app.utils.libro_diario import registrar_asiento_para_movimiento
from app.utils.caja_calculos import CUENTA_CAJA_CHICA, CUENTA_BANCO
from app.utils.turnos_caja import verificar_caja
from app.utils.bancos import banco_si_aplica
from app.deps import login_required

router = APIRouter()


def _cfg_facturacion(db: Session) -> ConfiguracionFacturacion:
    cfg = db.get(ConfiguracionFacturacion, 1)
    if not cfg:
        cfg = ConfiguracionFacturacion(id=1)
        db.add(cfg)
        db.flush()
    return cfg


def _isv_tasa(db: Session) -> Decimal:
    cfg = db.get(ConfiguracionFacturacion, 1)
    if cfg and cfg.isv_tasa is not None:
        return to_decimal(cfg.isv_tasa)
    return to_decimal(15)


def _error_fiscal(db: Session) -> str | None:
    from app.routers.facturacion import _validar_fiscal_disponible
    return _validar_fiscal_disponible(_cfg_facturacion(db))


@router.get("/pos")
def pos_index(request: Request, cotizacion: int = 0, db: Session = Depends(get_db), usuario=Depends(login_required)):
    productos = db.query(Producto).filter(Producto.estado == "activo", Producto.existencia > 0).order_by(Producto.nombre).all()
    clientes = db.query(Cliente).order_by(Cliente.nombre).all()
    # Venta desde una cotización: el carrito se carga con sus productos y
    # precios (sin ISV, igual que el carrito) y la venta queda ligada a ella.
    cot_datos = None
    if cotizacion:
        cot = db.get(Cotizacion, cotizacion)
        if cot and cot.estado == COTIZACION_VIGENTE:
            items = []
            for d in cot.detalles:
                p = db.get(Producto, d.producto_id) if d.producto_id else None
                if not p:
                    continue
                items.append({"id": p.id, "nombre": p.nombre, "categoria": p.categoria or "",
                              "precio": float(d.precio_unitario or 0), "precioLista": float(p.precio_venta or 0),
                              "cantidad": int(d.cantidad or 1), "existencia": int(p.existencia or 0)})
            cot_datos = {"id": cot.id, "numero": cot.numero, "cliente_id": cot.cliente_id, "items": items}
    return templates.TemplateResponse("pos/index.html", {
        "request": request, "productos": productos, "clientes": clientes, "usuario": usuario,
        "tasa_isv": _isv_tasa(db), "cotizacion": cot_datos,
        "error_fiscal": _error_fiscal(db),
        "clientes_rtn": {c.id: (c.rtn or "") for c in clientes if c.rtn and (c.rtn or "").lower() != "none"},
    })


def _partes_mixto(db: Session, venta_in: VentaIn, total: Decimal):
    """Pago mixto del POS: lo que vino con tarjeta y/o transferencia, y el
    resto en efectivo. Devuelve ([(forma, monto, banco_id, referencia)], efectivo)."""
    partes, no_efectivo = [], Decimal("0.00")
    for p in venta_in.pagos:
        forma = "Tarjeta" if "tarjeta" in (p.forma or "").lower() else "Transferencia" if p.forma == "Transferencia" else None
        monto = to_decimal(p.monto or 0).quantize(Decimal("0.01"))
        if not forma or monto <= 0:
            continue
        if monto < 0:
            raise ValueError("Los montos del pago mixto no pueden ser negativos.")
        ref = (p.referencia or "").strip()[:60]
        if forma == "Transferencia" and not ref:
            raise ValueError("Escribe el número de referencia de la transferencia.")
        partes.append((forma, monto, p.banco_id, ref))
        no_efectivo += monto
    if not partes:
        raise ValueError("En pago mixto escribe cuánto pagó con tarjeta y/o transferencia.")
    if no_efectivo > total:
        raise ValueError(f"Tarjeta + transferencia (L {no_efectivo:,.2f}) es más que el total (L {total:,.2f}).")
    efectivo = (total - no_efectivo).quantize(Decimal("0.01"))
    if efectivo > 0:
        partes.insert(0, ("Efectivo", efectivo, None, ""))
    if len(partes) < 2:
        raise ValueError("Todo se pagó de una sola forma: elige esa forma de pago en vez de «Mixto».")
    return partes, efectivo


@router.post("/pos/vender")
def pos_vender(request: Request, venta_in: VentaIn, db: Session = Depends(get_db), usuario=Depends(login_required)):
    mensaje_caja = verificar_caja(db)
    if mensaje_caja:
        return JSONResponse({"ok": False, "mensaje": mensaje_caja}, status_code=400)
    if not venta_in.items:
        return JSONResponse({"ok": False, "mensaje": "El carrito está vacío."}, status_code=400)
    tipo_doc = "fiscal" if venta_in.tipo_documento == "fiscal" else "interno"
    if tipo_doc == "fiscal":
        error_fiscal = _error_fiscal(db)
        if error_fiscal:
            return JSONResponse({"ok": False, "mensaje": error_fiscal}, status_code=400)

    subtotal = Decimal("0")
    detalles = []
    for item in venta_in.items:
        producto = db.get(Producto, item.producto_id)
        if not producto:
            return JSONResponse({"ok": False, "mensaje": f"Producto {item.producto_id} no encontrado."}, status_code=400)
        if item.cantidad > producto.existencia:
            return JSONResponse({"ok": False, "mensaje": f"No hay suficiente existencia de '{producto.nombre}'."}, status_code=400)
        # Si viene un precio_unitario (el cajero lo ajustó en el carrito), se
        # usa ese en vez del precio_venta del catálogo, igual que ya se
        # permite al agregar un repuesto a una orden de servicio.
        precio_lista = to_decimal(producto.precio_venta or 0)
        if item.precio_unitario is not None and item.precio_unitario > 0:
            precio = to_decimal(item.precio_unitario).quantize(Decimal("0.01"))
        else:
            precio = precio_lista
        # Se puede cambiar el precio al vender, pero nunca por debajo del
        # costo del producto (los dos sin ISV).
        costo = to_decimal(producto.costo or 0)
        if precio < costo:
            return JSONResponse({"ok": False, "mensaje": (
                f"El precio de '{producto.nombre}' no puede ser menor a su costo: "
                f"mínimo L {costo:,.2f} sin ISV (L {aplicar_impuesto(costo, _isv_tasa(db)):,.2f} con ISV).")}, status_code=400)
        sub = (precio * item.cantidad).quantize(Decimal("0.01"))
        subtotal += sub
        detalles.append((producto, item.cantidad, precio, sub, precio_lista))

    descuento = to_decimal(venta_in.descuento)
    if descuento < 0 or descuento > subtotal:
        return JSONResponse({"ok": False, "mensaje": "El descuento no es válido."}, status_code=400)

    total_neto = (subtotal - descuento).quantize(Decimal("0.01"))
    tasa = _isv_tasa(db)
    total = aplicar_impuesto(total_neto, tasa)
    isv_monto = (total - total_neto).quantize(Decimal("0.01"))
    monto_recibido = to_decimal(venta_in.monto_recibido)
    es_mixto = venta_in.forma_pago == "Mixto"
    partes = []  # (forma, monto, banco_id, referencia): una fila de ingreso por cada una
    if es_mixto:
        try:
            partes, efectivo_parte = _partes_mixto(db, venta_in, total)
        except ValueError as e:
            return JSONResponse({"ok": False, "mensaje": str(e)}, status_code=400)
        if monto_recibido < efectivo_parte:
            return JSONResponse({"ok": False, "mensaje": f"En efectivo debe pagar L {efectivo_parte:,.2f}: el monto recibido es menor."}, status_code=400)
        cambio = (monto_recibido - efectivo_parte).quantize(Decimal("0.01")) if efectivo_parte > 0 else Decimal("0.00")
        monto_recibido = (total + cambio).quantize(Decimal("0.01"))
    else:
        if (venta_in.forma_pago or "Efectivo") != "Efectivo":  # no_efectivo_recibe_total: transferencia/tarjeta = el total exacto
            monto_recibido = total
        if monto_recibido < total:
            return JSONResponse({"ok": False, "mensaje": "El monto recibido es menor al total a pagar."}, status_code=400)
        cambio = (monto_recibido - total).quantize(Decimal("0.01"))

    venta = Venta(
        numero_venta=generar_numero_venta(db), cliente_id=venta_in.cliente_id,
        subtotal=subtotal, descuento=descuento, total=total,
        forma_pago=venta_in.forma_pago, monto_recibido=monto_recibido, cambio=cambio,
        usuario_nombre=usuario["nombre_completo"],
    )
    db.add(venta)
    db.flush()

    for producto, cantidad, precio, sub, precio_lista in detalles:
        db.add(DetalleVenta(venta_id=venta.id, producto_id=producto.id, cantidad=cantidad,
                             precio_unitario=precio, subtotal=sub, precio_lista=precio_lista))
        producto.existencia -= cantidad
        db.add(MovimientoInventario(
            producto_id=producto.id, tipo="salida", cantidad=cantidad,
            existencia_resultante=producto.existencia, usuario_nombre=usuario["nombre_completo"],
            motivo=f"Venta {venta.numero_venta}",
        ))

    # Efectivo -> Caja Chica; cualquier otra forma de pago (Transferencia,
    # Tarjeta, Otro) -> Banco, porque ese dinero nunca pasó físicamente por
    # la caja (ver la misma regla en Caja y en Facturas de orden).
    # Pago mixto: una fila por forma, cada una en su lugar (el efectivo a la
    # caja, la tarjeta/transferencia al banco elegido) y el neto/ISV
    # repartidos en proporción para que cada asiento cuadre.
    if not partes:
        partes = [(venta.forma_pago, total, venta_in.banco_id, "")]
    isv_restante, neto_restante = isv_monto, total_neto
    for i, (forma, monto_parte, banco_parte, ref_parte) in enumerate(partes):
        ultima = i == len(partes) - 1
        isv_fila = isv_restante if ultima else (monto_parte * isv_monto / total).quantize(Decimal("0.01")) if total > 0 else Decimal("0.00")
        neto_fila = neto_restante if ultima else (monto_parte - isv_fila).quantize(Decimal("0.01"))
        isv_restante, neto_restante = isv_restante - isv_fila, neto_restante - neto_fila
        cuenta_venta = CUENTA_CAJA_CHICA if forma == "Efectivo" else CUENTA_BANCO
        mov_venta = MovimientoFinanciero(
            tipo="ingreso", categoria="Venta POS", monto=monto_parte,
            descripcion=f"Venta {venta.numero_venta}" + (f" (pago mixto: {forma})" if es_mixto else ""),
            usuario_nombre=usuario["nombre_completo"],
            referencia=venta.numero_venta, cuenta=cuenta_venta, metodo_pago=forma,
            banco_id=banco_si_aplica(db, cuenta_venta, banco_parte),
            num_referencia=ref_parte or None,
            estado_conciliacion="pendiente" if forma == "Transferencia" and ref_parte else None,
        )
        db.add(mov_venta)
        db.flush()
        registrar_asiento_para_movimiento(db, mov_venta, monto_neto=neto_fila, isv_monto=isv_fila)

    # Documento de la venta: se elige en el Punto de Venta entre comprobante
    # interno (no fiscal, el de siempre) o factura fiscal con CAI. Se emite de
    # una vez para que el cliente se lleve su constancia.
    cfg_fact = _cfg_facturacion(db)
    numero_documento, correlativo = generar_numero_factura(cfg_fact, tipo_doc)
    cliente_venta = db.get(Cliente, venta.cliente_id) if venta.cliente_id else None
    rtn = (venta_in.cliente_rtn or "").strip()
    if rtn.lower() == "none":
        rtn = ""
    if not rtn and cliente_venta and (cliente_venta.rtn or "").lower() != "none":
        rtn = cliente_venta.rtn or ""
    if cliente_venta and rtn and rtn != (cliente_venta.rtn or ""):
        cliente_venta.rtn = rtn  # queda en la ficha del cliente para la próxima vez
    fiscal = tipo_doc == "fiscal"
    recibo = Factura(
        venta_id=venta.id,
        tipo=tipo_doc,
        numero_documento=numero_documento,
        correlativo=correlativo,
        cai_usado=cfg_fact.cai if fiscal else None,
        rango_autorizado_inicio=cfg_fact.rango_autorizado_inicio if fiscal else None,
        rango_autorizado_fin=cfg_fact.rango_autorizado_fin if fiscal else None,
        fecha_limite_emision=cfg_fact.fecha_limite_emision if fiscal else None,
        rtn_emisor=cfg_fact.rtn_taller if fiscal else None,
        razon_social_emisor=(cfg_fact.razon_social or cfg_fact.nombre_comercial) if fiscal else None,
        cliente_nombre=cliente_venta.nombre if cliente_venta else "Consumidor final",
        cliente_rtn=rtn,
        cliente_direccion=(cliente_venta.direccion or "") if cliente_venta else "",
        fecha_emision=datetime.utcnow(),
        subtotal=subtotal,
        descuento=descuento,
        importe_exento=Decimal("0.00"),
        importe_gravado=total_neto,
        isv_tasa=tasa,
        isv_monto=isv_monto,
        total=total,
        usuario_nombre=usuario["nombre_completo"],
    )
    db.add(recibo)
    db.flush()

    if venta_in.cotizacion_id:
        cot = db.get(Cotizacion, venta_in.cotizacion_id)
        if cot and cot.estado == COTIZACION_VIGENTE:
            cot.estado = COTIZACION_ACEPTADA
            cot.venta_id = venta.id

    db.commit()
    return JSONResponse({
        "ok": True, "numero_venta": venta.numero_venta,
        "total": float(total), "isv": float(isv_monto), "cambio": float(cambio),
        "factura_id": recibo.id, "numero_documento": recibo.numero_documento, "tipo_documento": tipo_doc,
    })
