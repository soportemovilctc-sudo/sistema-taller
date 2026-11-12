"""Pago mixto: el cliente paga una parte en efectivo y otra con tarjeta o
transferencia (o las tres).

Cada parte va a su lugar, como si fueran cobros separados:
* Efectivo → la Caja Chica (la cajera solo ve esta parte en su caja).
* Tarjeta / Transferencia → el banco elegido para esa parte (la tarjeta
  genera sola su comisión del POS, ver comision_tarjeta.py).

Los formularios mandan siempre los mismos campos (ver
templates/_pago_mixto.html): mx_efectivo, mx_tarjeta, mx_banco_tarjeta,
mx_transferencia, mx_banco_transferencia y mx_ref_transferencia."""
from decimal import Decimal, InvalidOperation

from app.utils.calculations import to_decimal

FORMA_MIXTO = "Mixto"
CERO = Decimal("0.00")


def _monto(texto, nombre) -> Decimal:
    t = str(texto or "").replace(",", "").replace("L", "").strip()
    if not t:
        return CERO
    try:
        v = to_decimal(t).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError(f"El monto en {nombre} no es válido.")
    if v < 0:
        raise ValueError(f"El monto en {nombre} no puede ser negativo.")
    return v


def leer_partes(*, efectivo="", tarjeta="", banco_tarjeta="", transferencia="", banco_transferencia="",
                ref_transferencia="", forma_tarjeta: str = "Tarjeta") -> list[dict]:
    """Partes con monto > 0, en orden Efectivo, Tarjeta, Transferencia.
    Cada parte: {forma, monto, banco_raw, referencia}. Lanza ValueError si
    algo no cuadra (montos inválidos, transferencia sin referencia, menos de
    dos formas)."""
    ref = (ref_transferencia or "").strip()[:60]
    partes = []
    for forma, valor, banco, referencia, nombre in (
        ("Efectivo", efectivo, "", "", "efectivo"),
        (forma_tarjeta, tarjeta, banco_tarjeta, "", "tarjeta"),
        ("Transferencia", transferencia, banco_transferencia, ref, "transferencia"),
    ):
        m = _monto(valor, nombre)
        if m > 0:
            partes.append({"forma": forma, "monto": m, "banco_raw": banco, "referencia": referencia})
    if len(partes) < 2:
        raise ValueError("En pago mixto escribe al menos dos partes (por ejemplo efectivo y tarjeta). "
                         "Si paga todo de una forma, elige esa forma.")
    if any(p["forma"] == "Transferencia" for p in partes) and not ref:
        raise ValueError("Escribe el número de referencia de la transferencia.")
    return partes


def total(partes) -> Decimal:
    return sum((p["monto"] for p in partes), CERO)


def texto(partes, moneda="L") -> str:
    return " + ".join(f"{p['forma']} {moneda} {p['monto']:,.2f}" for p in partes)


def exigir_total(partes, esperado, que="el saldo") -> None:
    esperado = to_decimal(esperado).quantize(Decimal("0.01"))
    suma = total(partes)
    if suma != esperado:
        dif = esperado - suma
        raise ValueError(f"Las partes suman L {suma:,.2f} y {que} es L {esperado:,.2f}: "
                         + (f"faltan L {dif:,.2f}." if dif > 0 else f"sobran L {-dif:,.2f}."))
