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
    if sol.estado == COMPRA_ANULADA:
        return "Esta solicitud ya está anulada."
    if not (motivo or "").strip():
        return "Escribe el motivo."
    if any(not r.anulada for r in sol.recepciones):
        error = anular_recepciones(db, sol, motivo, usuario_nombre)
        if error:
            return error
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


def agregar_isv_recepcion(db: Session, rec: RecepcionCompra, tasa, usuario_nombre: str) -> tuple:
    """Corrige una recepción que se guardó sin ISV cuando la factura del
    proveedor sí lo traía: le suma el ISV (tasa % de la mercadería) al total.
      * Si se pagó completa al recibirla (efectivo o banco), ese pago sube
        al total con ISV y se rehace su asiento; si salió de una caja ya
        cerrada, se recalcula su arqueo y queda en su bitácora.
      * Si fue al crédito o se pagó en partes, el ISV queda por pagar.
    Devuelve (error | None, mensaje). No hace commit."""
    from app.models import TurnoCaja, TurnoCajaEvento, TURNO_ABIERTO
    from app.utils.libro_diario import eliminar_asiento_de_movimiento
    if rec.anulada:
        return "Esta compra está anulada.", ""
    if to_decimal(rec.isv or 0) > 0:
        return "Esta recepción ya tiene ISV registrado.", ""
    subtotal = to_decimal(rec.subtotal or 0)
    isv = (subtotal * to_decimal(tasa) / 100).quantize(CENT)
    if isv <= 0:
        return "La recepción no tiene mercadería con costo para calcular el ISV.", ""
    total_antes = to_decimal(rec.total or 0).quantize(CENT)
    rec.isv = isv
    rec.total = (subtotal + isv).quantize(CENT)
    pagos = (db.query(MovimientoFinanciero)
             .filter(MovimientoFinanciero.recepcion_compra_id == rec.id,
                     MovimientoFinanciero.excluir_de_contabilidad == False)  # noqa: E712
             .order_by(MovimientoFinanciero.id).all())
    pagado = sum((to_decimal(m.monto) for m in pagos), CERO).quantize(CENT)
    if rec.forma_pago != PAGO_COMPRA_CREDITO and len(pagos) == 1 and pagado == total_antes:
        m = pagos[0]
        m.monto = (to_decimal(m.monto) + isv).quantize(CENT)
        if "con ISV" not in (m.descripcion or ""):
            m.descripcion = f"{m.descripcion or ''} (con ISV {isv:,.2f})".strip()
        rec.pagado = (to_decimal(rec.pagado or 0) + isv).quantize(CENT)
        db.flush()
        eliminar_asiento_de_movimiento(db, m.id)
        registrar_asiento_para_movimiento(db, m)
        t = db.get(TurnoCaja, m.turno_caja_id) if m.turno_caja_id else None
        if t and t.estado != TURNO_ABIERTO:
            from app.routers.turnos_caja import _recalcular_arqueo
            antes_e = to_decimal(t.efectivo_esperado or 0)
            _recalcular_arqueo(db, t)
            db.add(TurnoCajaEvento(turno_id=t.id, accion="edicion", usuario_nombre=usuario_nombre, fecha=datetime.utcnow(),
                                   detalle=(f"Se agregó el ISV (L {isv:,.2f}) a la compra {rec.numero}: su pago pasó de L {total_antes:,.2f} "
                                            f"a L {m.monto:,.2f}. Esperado: L {antes_e:,.2f} → L {to_decimal(t.efectivo_esperado):,.2f}")))
        donde = "de la caja" if m.cuenta == CUENTA_CAJA_CHICA else "del banco"
        return None, f"Se agregó el ISV de L {isv:,.2f}. El pago {donde} ahora es L {m.monto:,.2f} (total de la factura)."
    db.flush()
    return None, f"Se agregó el ISV de L {isv:,.2f}. Total de la factura: L {rec.total:,.2f}; quedan L {rec.total - to_decimal(rec.pagado or 0):,.2f} por pagar al proveedor."


def pagar_recepcion(db: Session, rec: RecepcionCompra, monto_texto: str, forma: str, nota: str, usuario_nombre: str) -> str | None:
    if rec.anulada:
        return "Esta compra fue anulada: ya no se le puede pagar."
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
        RecepcionCompra.fecha >= inicio, RecepcionCompra.fecha < fin, RecepcionCompra.anulada == False).one()  # noqa: E712
    return {"subtotal": to_decimal(sub).quantize(CENT), "isv": to_decimal(isv).quantize(CENT)}


def por_pagar_a(db: Session, instante: datetime) -> Decimal:
    """Lo que se le debe a proveedores por compras recibidas hasta `instante`."""
    total = db.query(func.coalesce(func.sum(RecepcionCompra.total), 0)).filter(
        RecepcionCompra.fecha < instante, RecepcionCompra.anulada == False).scalar()  # noqa: E712
    pagado = db.query(func.coalesce(func.sum(MovimientoFinanciero.monto), 0)).filter(
        MovimientoFinanciero.recepcion_compra_id.isnot(None), MovimientoFinanciero.fecha < instante,
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ).scalar()
    return max(CERO, (to_decimal(total) - to_decimal(pagado)).quantize(CENT))



# ---------------------------------------------------------------------------
# Anular una compra ya recibida
# ---------------------------------------------------------------------------
def anular_recepciones(db: Session, sol: SolicitudCompra, motivo: str, usuario_nombre: str) -> str | None:
    """Deshace todo lo que hicieron las recepciones de la solicitud, como si la
    compra no hubiera existido en la contabilidad:
      * Inventario: salen las unidades que entraron (si todavía están), con su
        movimiento de salida; el costo y el precio de venta regresan a los de
        antes (si nadie los cambió después; si cambiaron, el costo se
        recalcula quitando esta compra del promedio).
      * Dinero: los pagos al proveedor dejan de contar (se excluyen de la
        contabilidad y se borra su asiento); si alguno salió de una caja ya
        cerrada, se recalcula su arqueo y queda en su bitácora.
      * La deuda con el proveedor desaparece y la compra deja de contar en
        reportes, ISV y Estados Financieros.
    Nada se borra de la base: todo queda marcado como anulado. No hace commit."""
    from app.models import TurnoCaja, TurnoCajaEvento, TURNO_ABIERTO
    from app.utils.libro_diario import eliminar_asiento_de_movimiento
    vivas = [r for r in sol.recepciones if not r.anulada]
    # 1) ¿Todavía están las unidades?
    necesita = {}
    for r in vivas:
        for d in r.detalles:
            necesita[d.producto_id] = necesita.get(d.producto_id, 0) + (d.cantidad or 0)
    faltan = []
    for pid, cant in necesita.items():
        p = db.get(Producto, pid)
        if p and (p.existencia or 0) < cant:
            faltan.append(f"{p.codigo} (entraron {cant}, quedan {p.existencia})")
    if faltan:
        return ("No se puede anular: parte de lo que entró ya se vendió o se usó: " + ", ".join(faltan)
                + ". Haz un ajuste de inventario o una devolución parcial en vez de anular.")
    ahora = datetime.utcnow()
    turnos = {}
    for r in sorted(vivas, key=lambda x: x.id, reverse=True):
        for d in r.detalles:
            p = db.get(Producto, d.producto_id)
            if not p:
                continue
            exist_antes = p.existencia or 0
            costo_act = to_decimal(p.costo or 0)
            p.existencia = exist_antes - (d.cantidad or 0)
            if costo_act.quantize(CENT) == to_decimal(d.costo_nuevo or 0).quantize(CENT):
                p.costo = to_decimal(d.costo_anterior or 0).quantize(CENT)
            elif p.existencia > 0:
                nuevo = (costo_act * exist_antes - to_decimal(d.costo_unitario or 0) * (d.cantidad or 0)) / p.existencia
                if nuevo > 0:
                    p.costo = nuevo.quantize(CENT)
            if d.precio_anterior is not None and d.precio_nuevo is not None and \
                    to_decimal(p.precio_venta or 0).quantize(CENT) == to_decimal(d.precio_nuevo).quantize(CENT):
                p.precio_venta = to_decimal(d.precio_anterior).quantize(CENT)
            db.add(MovimientoInventario(
                producto_id=p.id, tipo="salida", cantidad=d.cantidad, existencia_anterior=exist_antes,
                existencia_resultante=p.existencia, costo_unitario=d.costo_unitario, usuario_nombre=usuario_nombre,
                motivo=f"Anulación de la compra {sol.numero} ({r.numero}): {motivo.strip()}", fecha=ahora,
            ))
        for m in db.query(MovimientoFinanciero).filter(MovimientoFinanciero.recepcion_compra_id == r.id,
                                                       MovimientoFinanciero.excluir_de_contabilidad == False).all():  # noqa: E712
            m.excluir_de_contabilidad = True
            m.descripcion = f"{m.descripcion or ''} (ANULADO: compra anulada por {usuario_nombre})".strip()
            eliminar_asiento_de_movimiento(db, m.id)
            if m.turno_caja_id:
                turnos.setdefault(m.turno_caja_id, CERO)
                turnos[m.turno_caja_id] += to_decimal(m.monto)
        r.anulada, r.anulada_en, r.anulada_por, r.motivo_anulacion = True, ahora, usuario_nombre, motivo.strip()
    db.flush()
    for turno_id, monto in turnos.items():
        t = db.get(TurnoCaja, turno_id)
        if t and t.estado != TURNO_ABIERTO:
            from app.routers.turnos_caja import _recalcular_arqueo
            antes_e = to_decimal(t.efectivo_esperado or 0)
            _recalcular_arqueo(db, t)
            db.add(TurnoCajaEvento(turno_id=t.id, accion="edicion", usuario_nombre=usuario_nombre, fecha=ahora,
                                   detalle=(f"Se anuló la compra {sol.numero}: su pago de L {monto:,.2f} ya no cuenta en esta caja. "
                                            f"Esperado: L {antes_e:,.2f} → L {to_decimal(t.efectivo_esperado):,.2f}")))
    return None
