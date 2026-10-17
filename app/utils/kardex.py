"""Kardex (historial detallado) de un producto: cada entrada y salida, con
su documento, costo y el saldo de unidades que quedó después."""
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import MovimientoInventario, Producto
from app.utils.calculations import to_decimal
from app.utils.turnos_caja import inicio_dia_local_en_utc

CERO = Decimal("0.00")


def _fecha(valor: str):
    try:
        return datetime.strptime((valor or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _tipo(m: MovimientoInventario, cambio: int) -> str:
    motivo = (m.motivo or "")
    if motivo.startswith("Compra "):
        return "Compra"
    if motivo.startswith("Venta "):
        return "Venta"
    if m.ajuste_id or m.tipo == "ajuste":
        return "Ajuste"
    if "rden" in motivo:  # "Orden ...", "orden OS-..."
        return "Orden" if cambio < 0 else "Devolución de orden"
    return "Entrada" if cambio > 0 else "Salida"


def kardex_producto(db: Session, producto: Producto, desde_txt: str = "", hasta_txt: str = "") -> dict:
    movs = (db.query(MovimientoInventario).filter(MovimientoInventario.producto_id == producto.id)
            .order_by(MovimientoInventario.fecha.asc(), MovimientoInventario.id.asc()).all())
    desde, hasta = _fecha(desde_txt), _fecha(hasta_txt)
    inicio = inicio_dia_local_en_utc(desde) if desde else None
    fin = inicio_dia_local_en_utc(hasta + timedelta(days=1)) if hasta else None

    filas, anterior_saldo = [], None
    saldo_inicial = None
    for m in movs:
        antes = m.existencia_anterior
        if antes is None:
            if m.tipo == "entrada":
                antes = m.existencia_resultante - (m.cantidad or 0)
            elif m.tipo == "salida":
                antes = m.existencia_resultante + (m.cantidad or 0)
            else:
                antes = anterior_saldo if anterior_saldo is not None else m.existencia_resultante
        cambio = (m.existencia_resultante or 0) - (antes or 0)
        anterior_saldo = m.existencia_resultante
        if inicio and m.fecha < inicio:
            saldo_inicial = m.existencia_resultante
            continue
        if fin and m.fecha >= fin:
            continue
        if saldo_inicial is None:
            saldo_inicial = antes
        costo = to_decimal(m.costo_unitario) if m.costo_unitario is not None else None
        filas.append({
            "fecha": m.fecha, "tipo": _tipo(m, cambio), "documento": m.motivo or "", "usuario": m.usuario_nombre or "",
            "entrada": cambio if cambio > 0 else 0, "salida": -cambio if cambio < 0 else 0,
            "saldo": m.existencia_resultante, "costo": costo,
            "valor": (costo * abs(cambio)).quantize(Decimal("0.01")) if costo is not None else None,
        })
    entradas = sum(f["entrada"] for f in filas)
    salidas = sum(f["salida"] for f in filas)
    costo_actual = to_decimal(producto.costo or 0)
    return {
        "filas": list(reversed(filas)),  # lo más reciente arriba
        "entradas": entradas, "salidas": salidas,
        "saldo_inicial": saldo_inicial if saldo_inicial is not None else (producto.existencia or 0),
        "saldo_final": filas[-1]["saldo"] if filas else (producto.existencia or 0),
        "desde": desde_txt or "", "hasta": hasta_txt or "",
        "costo": costo_actual, "valor": (costo_actual * (producto.existencia or 0)).quantize(Decimal("0.01")),
        "cuadra": (not filas) or desde or hasta or filas[-1]["saldo"] == (producto.existencia or 0),
    }
