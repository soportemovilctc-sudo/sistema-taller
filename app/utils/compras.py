"""Compras: solicitud de compra -> recepción (confirmación) -> pago.

  * Las unidades SOLO entran al inventario con una recepción. Una solicitud
    se puede recibir en varias veces (lo que llegó cada vez); lo que no
    llegue se puede dar por cerrado.
  * Al recibir, el costo del producto queda en el costo PROMEDIO ponderado
    entre lo que había y lo que entra (costos sin ISV).
  * El pago se elige al recibir: Efectivo (sale de la caja abierta), Banco
    (transferencia) o Crédito (queda por pagar y se paga después, en una o
    varias veces). Cada pago es un egreso «Compras» vinculado a su
    recepción (MovimientoFinanciero.recepcion_compra_id).
  * Nada se borra: una solicitud sin nada recibido se anula; una recepción
    queda siempre en el historial.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Producto, MovimientoInventario, MovimientoFinanciero,
    SolicitudCompra, SolicitudCompraDetalle, RecepcionCompra, RecepcionCompraDetalle,
    COMPRA_PENDIENTE, COMPRA_PARCIAL, COMPRA_RECIBIDA, COMPRA_CERRADA, COMPRA_ANULADA,
    PAGO_COMPRA_EFECTIVO, PAGO_COMPRA_BANCO, PAGO_COMPRA_CREDITO, FORMAS_PAGO_COMPRA,
    CATEGORIA_COMPRA_MERCADERIA,
)
from app.utils.calculations import to_decimal
from app.utils.numbering import siguiente_numero
from app.utils.libro_diario import registrar_asiento_para_movimiento
from app.utils.caja_calculos import CUENTA_CAJA_CHICA, CUENTA_BANCO
from app.utils.turnos_caja import verificar_caja

CERO = Decimal("0.00")
CENT = Decimal("0.01")


def _num(valor, nombre: str, entero=False):
    texto = str(valor if valor is not None else "").strip().replace(",", "")
    if texto == "":
        return None
    try:
        n = int(texto) if entero else to_decimal(texto)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{nombre}: escribe un número válido.")
    if n < 0:
        raise ValueError(f"{nombre}: no puede ser negativo.")
    return n


def quitar_isv(valor, tasa) -> Decimal:
    """Valor escrito CON ISV incluido -> el mismo valor sin ISV."""
    return (to_decimal(valor) / (1 + to_decimal(tasa) / 100)).quantize(CENT)


def _sin_isv(valor, con_isv: bool, tasa):
    if valor is None:
        return None
    return quitar_isv(valor, tasa) if con_isv else to_decimal(valor).quantize(CENT)


def _siguiente(db: Session, modelo, prefijo: str) -> str:
    ultimo = db.query(modelo).order_by(modelo.id.desc()).first()
    return siguiente_numero(ultimo.numero if ultimo else None, prefijo)


# ---------------------------------------------------------------------------
# Solicitud
# ---------------------------------------------------------------------------
def crear_solicitud(db: Session, proveedor: str, notas: str, lineas: list[dict], usuario_nombre: str,
                    costo_con_isv: bool = False, precio_con_isv: bool = False, tasa=15):
    """lineas: [{producto_id, cantidad, costo, precio?}] -> (solicitud, errores).
    costo_con_isv / precio_con_isv: lo escrito ya trae el ISV y se le quita."""
    errores, filas, vistos = [], [], set()
    if not (proveedor or "").strip():
        errores.append("Escribe el proveedor.")
    for i, l in enumerate(lineas, start=1):
        try:
            pid = int(l.get("producto_id"))
            cantidad = _num(l.get("cantidad"), f"Línea {i} (cantidad)", entero=True)
            costo = _sin_isv(_num(l.get("costo"), f"Línea {i} (costo)"), costo_con_isv, tasa)
            precio = _sin_isv(_num(l.get("precio"), f"Línea {i} (precio de venta)"), precio_con_isv, tasa)
        except (TypeError, ValueError) as e:
            errores.append(str(e) if isinstance(e, ValueError) and str(e) else f"Línea {i}: datos inválidos.")
            continue
        producto = db.get(Producto, pid)
        if not producto or producto.estado != "activo":
            errores.append(f"Línea {i}: el producto no existe o está inactivo.")
            continue
        if pid in vistos:
            errores.append(f"{producto.codigo} está repetido.")
            continue
        vistos.add(pid)
        if not cantidad:
            errores.append(f"{producto.codigo}: la cantidad debe ser mayor a cero.")
            continue
        costo = (costo if costo is not None else to_decimal(producto.costo or 0)).quantize(CENT)
        if precio is not None and precio > 0 and precio < costo:
            errores.append(f"{producto.codigo}: el precio de venta (L {precio:,.2f} sin ISV) queda por debajo del costo (L {costo:,.2f}).")
            continue
        filas.append((producto, cantidad, costo, precio if precio else None))
    if not filas and not errores:
        errores.append("Agrega al menos un producto.")
    if errores:
        return None, errores
    sol = SolicitudCompra(
        numero=_siguiente(db, SolicitudCompra, "SC"), fecha=datetime.utcnow(),
        proveedor=proveedor.strip(), notas=(notas or "").strip(), estado=COMPRA_PENDIENTE,
        usuario_nombre=usuario_nombre,
        total_estimado=sum((c * k for _, c, k, _p in filas), CERO).quantize(CENT),
    )
    for producto, cantidad, costo, precio in filas:
        sol.detalles.append(SolicitudCompraDetalle(producto_id=producto.id, cantidad=cantidad, costo_unitario=costo, precio_venta=precio))
    db.add(sol)
    db.flush()
    return sol, []


def anular_solicitud(db: Session, sol: SolicitudCompra, motivo: str, usuario_nombre: str) -> str | None:
    if sol.estado != COMPRA_PENDIENTE or sol.recepciones:
        return "Solo se anula una solicitud a la que todavía no se le ha recibido nada."
    if not (motivo or "").strip():
        return "Escribe el motivo."
    sol.estado = COMPRA_ANULADA
    sol.cerrada_en, sol.cerrada_por, sol.motivo_cierre = datetime.utcnow(), usuario_nombre, motivo.strip()
    return None


def cerrar_solicitud(db: Session, sol: SolicitudCompra, motivo: str, usuario_nombre: str) -> str | None:
    if sol.estado != COMPRA_PARCIAL:
        return "Solo se cierra una solicitud recibida en parte."
    if not (motivo or "").strip():
        return "Escribe el motivo (por ejemplo: el proveedor no tenía el resto)."
    sol.estado = COMPRA_CERRADA
    sol.cerrada_en, sol.cerrada_por, sol.motivo_cierre = datetime.utcnow(), usuario_nombre, motivo.strip()
    return None


# ---------------------------------------------------------------------------
# Pagos
# ---------------------------------------------------------------------------
def _registrar_pago(db: Session, rec: RecepcionCompra, monto: Decimal, forma: str, usuario_nombre: str, nota: str = ""):
    efectivo = forma == PAGO_COMPRA_EFECTIVO
    mov = MovimientoFinanciero(
        tipo="gasto", categoria=CATEGORIA_COMPRA_MERCADERIA, monto=monto.quantize(CENT),
        descripcion=(f"Pago de compra {rec.numero} ({rec.solicitud.numero}) · {rec.proveedor}"
                     + (f" · Factura {rec.factura_proveedor}" if rec.factura_proveedor else "")
                     + (f" · {nota.strip()}" if nota and nota.strip() else "")),
        usuario_nombre=usuario_nombre, referencia=rec.numero,
        cuenta=CUENTA_CAJA_CHICA if efectivo else CUENTA_BANCO,
        metodo_pago="Efectivo" if efectivo else "Transferencia",
        recepcion_compra_id=rec.id, fecha=datetime.utcnow(),
    )
    db.add(mov)
    db.flush()
    registrar_asiento_para_movimiento(db, mov)
    rec.pagado = (to_decimal(rec.pagado or 0) + mov.monto).quantize(CENT)
    return mov


def pagar_recepcion(db: Session, rec: RecepcionCompra, monto_texto: str, forma: str, nota: str, usuario_nombre: str) -> str | None:
    try:
        monto = _num(monto_texto, "Monto")
    except ValueError as e:
        return str(e)
    saldo = to_decimal(rec.total or 0) - to_decimal(rec.pagado or 0)
    if not monto or monto <= 0:
        return "Escribe el monto a pagar."
    if monto > saldo:
        return f"El pago no puede ser mayor al saldo pendiente (L {saldo:,.2f})."
    if forma not in (PAGO_COMPRA_EFECTIVO, PAGO_COMPRA_BANCO):
        return "Elige si se paga en efectivo o por banco."
    if forma == PAGO_COMPRA_EFECTIVO:
        mensaje = verificar_caja(db)
        if mensaje:
            return mensaje
    _registrar_pago(db, rec, monto, forma, usuario_nombre, nota)
    return None


# ---------------------------------------------------------------------------
# Recepción
# ---------------------------------------------------------------------------
def recibir(db: Session, sol: SolicitudCompra, lineas: dict, forma_pago: str, factura_proveedor: str,
            isv_texto: str, notas: str, usuario_nombre: str,
            costo_con_isv: bool = False, precio_con_isv: bool = False, tasa=15):
    """lineas: {detalle_id: (cantidad, costo[, precio])} -> (recepcion, errores).
    El precio de venta (si se escribe, o el de la solicitud) queda en el
    producto al recibir."""
    if sol.estado not in (COMPRA_PENDIENTE, COMPRA_PARCIAL):
        return None, ["Esta solicitud ya no se puede recibir."]
    errores = []
    if forma_pago not in FORMAS_PAGO_COMPRA:
        errores.append("Elige cómo se pagó.")
    try:
        isv = (_num(isv_texto, "ISV") or CERO).quantize(CENT)
    except ValueError as e:
        errores.append(str(e))
        isv = CERO
    filas = []
    for det in sol.detalles:
        valores = tuple(lineas.get(det.id, ("", ""))) + ("",)
        cant_txt, costo_txt, precio_txt = valores[0], valores[1], valores[2]
        try:
            cantidad = _num(cant_txt, f"{det.producto.codigo} (cantidad)", entero=True) or 0
            costo = _sin_isv(_num(costo_txt, f"{det.producto.codigo} (costo)"), costo_con_isv, tasa)
            precio = _sin_isv(_num(precio_txt, f"{det.producto.codigo} (precio de venta)"), precio_con_isv, tasa)
        except ValueError as e:
            errores.append(str(e))
            continue
        if cantidad == 0:
            continue
        if cantidad > det.pendiente:
            errores.append(f"{det.producto.codigo}: solo faltan {det.pendiente} por recibir.")
            continue
        costo = (costo if costo is not None else to_decimal(det.costo_unitario)).quantize(CENT)
        if not precio:
            precio = to_decimal(det.precio_venta) if det.precio_venta else None
        if precio is not None and precio < costo:
            errores.append(f"{det.producto.codigo}: el precio de venta (L {precio:,.2f} sin ISV) queda por debajo del costo (L {costo:,.2f}).")
            continue
        filas.append((det, cantidad, costo, precio))
    if not filas and not errores:
        errores.append("Escribe la cantidad que llegó de al menos un producto.")
    if forma_pago == PAGO_COMPRA_EFECTIVO and not errores:
        mensaje = verificar_caja(db)
        if mensaje:
            errores.append(mensaje)
    if errores:
        return None, errores

    rec = RecepcionCompra(
        numero=_siguiente(db, RecepcionCompra, "RC"), solicitud_id=sol.id, fecha=datetime.utcnow(),
        proveedor=sol.proveedor, factura_proveedor=(factura_proveedor or "").strip(),
        forma_pago=forma_pago, notas=(notas or "").strip(), usuario_nombre=usuario_nombre, pagado=CERO,
    )
    db.add(rec)
    db.flush()
    subtotal = CERO
    for det, cantidad, costo, precio in filas:
        producto = db.query(Producto).filter(Producto.id == det.producto_id).with_for_update().first()
        existencia_ant = producto.existencia or 0
        costo_ant = to_decimal(producto.costo or 0)
        if existencia_ant > 0 and costo_ant > 0:
            costo_nuevo = ((costo_ant * existencia_ant + costo * cantidad) / (existencia_ant + cantidad)).quantize(CENT)
        else:
            costo_nuevo = costo
        producto.existencia = existencia_ant + cantidad
        producto.costo = costo_nuevo
        precio_ant = to_decimal(producto.precio_venta or 0)
        if precio is not None:
            producto.precio_venta = precio
        if sol.proveedor and not (producto.proveedor or "").strip():
            producto.proveedor = sol.proveedor
        linea = (costo * cantidad).quantize(CENT)
        subtotal += linea
        rec.detalles.append(RecepcionCompraDetalle(
            producto_id=producto.id, cantidad=cantidad, costo_unitario=costo, subtotal=linea,
            existencia_anterior=existencia_ant, costo_anterior=costo_ant, costo_nuevo=costo_nuevo,
            precio_anterior=precio_ant, precio_nuevo=to_decimal(producto.precio_venta or 0),
        ))
        db.add(MovimientoInventario(
            producto_id=producto.id, tipo="entrada", cantidad=cantidad,
            existencia_anterior=existencia_ant, existencia_resultante=producto.existencia,
            costo_unitario=costo, usuario_nombre=usuario_nombre,
            motivo=f"Compra {rec.numero} ({sol.numero}) · {sol.proveedor}",
        ))
        det.cantidad_recibida = (det.cantidad_recibida or 0) + cantidad

    rec.subtotal = subtotal.quantize(CENT)
    rec.isv = isv
    rec.total = (subtotal + isv).quantize(CENT)
    sol.estado = COMPRA_RECIBIDA if all(d.pendiente == 0 for d in sol.detalles) else COMPRA_PARCIAL
    if forma_pago != PAGO_COMPRA_CREDITO and rec.total > 0:
        _registrar_pago(db, rec, to_decimal(rec.total), forma_pago, usuario_nombre)
    db.flush()
    return rec, []


# ---------------------------------------------------------------------------
# Para los Estados Financieros
# ---------------------------------------------------------------------------
def compras_recibidas(db: Session, inicio: datetime, fin: datetime) -> dict:
    """Mercadería recibida en el período (al costo, sin ISV) y su ISV."""
    sub, isv = db.query(func.coalesce(func.sum(RecepcionCompra.subtotal), 0), func.coalesce(func.sum(RecepcionCompra.isv), 0)).filter(
        RecepcionCompra.fecha >= inicio, RecepcionCompra.fecha < fin).one()
    return {"subtotal": to_decimal(sub).quantize(CENT), "isv": to_decimal(isv).quantize(CENT)}


def por_pagar_a(db: Session, instante: datetime) -> Decimal:
    """Lo que se le debe a proveedores por compras recibidas hasta `instante`."""
    total = db.query(func.coalesce(func.sum(RecepcionCompra.total), 0)).filter(RecepcionCompra.fecha < instante).scalar()
    pagado = db.query(func.coalesce(func.sum(MovimientoFinanciero.monto), 0)).filter(
        MovimientoFinanciero.recepcion_compra_id.isnot(None), MovimientoFinanciero.fecha < instante,
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ).scalar()
    return max(CERO, (to_decimal(total) - to_decimal(pagado)).quantize(CENT))
