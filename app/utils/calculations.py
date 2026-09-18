"""Cálculos financieros de las órdenes de servicio.

Reglas (ver especificación del proyecto):
    Recargo = Cotización * porcentaje / 100
    Total   = Cotización + Recargo
    Saldo   = Total - pagos realizados

No se permiten valores negativos ni abonos mayores al saldo pendiente.
"""
from decimal import Decimal, ROUND_HALF_UP


def to_decimal(value) -> Decimal:
    if value is None:
        value = 0
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def calcular_recargo(cotizacion, porcentaje) -> Decimal:
    cotizacion = to_decimal(cotizacion)
    porcentaje = to_decimal(porcentaje)
    if cotizacion < 0 or porcentaje < 0:
        raise ValueError("Los valores no pueden ser negativos")
    recargo = cotizacion * porcentaje / Decimal(100)
    return recargo.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_total(cotizacion, recargo, repuestos_subtotal=0) -> Decimal:
    cotizacion = to_decimal(cotizacion)
    recargo = to_decimal(recargo)
    repuestos_subtotal = to_decimal(repuestos_subtotal)
    total = cotizacion + recargo + repuestos_subtotal
    if total < 0:
        raise ValueError("El total no puede ser negativo")
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_saldo(total, abonado) -> Decimal:
    total = to_decimal(total)
    abonado = to_decimal(abonado)
    saldo = total - abonado
    if saldo < 0:
        saldo = Decimal("0.00")
    return saldo.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validar_abono(monto, saldo_actual) -> Decimal:
    monto = to_decimal(monto)
    saldo_actual = to_decimal(saldo_actual)
    if monto <= 0:
        raise ValueError("El abono debe ser mayor a cero")
    if monto > saldo_actual:
        raise ValueError("El abono no puede ser mayor al saldo pendiente")
    return monto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def recalcular_orden(orden):
    """Recalcula recargo, repuestos, total y saldo de una orden (objeto
    SQLAlchemy) en memoria. No hace commit; quien llama decide cuándo guardar.
    El recargo se aplica solo sobre la cotización del servicio; los
    repuestos ya llevan su propio precio de venta del inventario.
    """
    recargo = calcular_recargo(orden.cotizacion, orden.recargo_pct)
    repuestos_subtotal = sum((to_decimal(r.subtotal) for r in orden.repuestos), Decimal("0.00"))
    total = calcular_total(orden.cotizacion, recargo, repuestos_subtotal)
    abonado = sum((to_decimal(p.monto) for p in orden.pagos), Decimal("0.00"))
    saldo = calcular_saldo(total, abonado)

    orden.recargo_monto = recargo
    orden.repuestos_subtotal = repuestos_subtotal
    orden.total = total
    orden.abonado = abonado
    orden.saldo = saldo
    return orden
