"""Cálculos del módulo de Caja: saldo consolidado (Liquidez Total) y
reporte de rentabilidad (Utilidad Neta), a partir del mismo libro de
movimientos financieros que ya usan Contabilidad y Reportes.

Reglas (ver especificación del proyecto):
    Liquidez Total = saldo_inicial_caja_chica + saldo_inicial_banco
                      + ingresos_totales_del_mes - egresos_totales_del_mes
    Utilidad Neta   = ingresos_devengados/cobrados_del_periodo
                      - egresos/gastos_del_periodo
    (la Utilidad Neta se calcula totalmente independiente de los saldos
    iniciales: es rentabilidad, no efectivo disponible).
"""
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import MovimientoFinanciero, SaldoInicialMensual
from app.utils.calculations import to_decimal

CUENTA_CAJA_CHICA = "caja_chica"
CUENTA_BANCO = "banco"


def mes_actual() -> tuple[int, int]:
    hoy = date.today()
    return hoy.year, hoy.month


def obtener_saldo_inicial(db: Session, anio: int, mes: int) -> SaldoInicialMensual | None:
    return db.query(SaldoInicialMensual).filter(
        SaldoInicialMensual.anio == anio, SaldoInicialMensual.mes == mes
    ).first()


def guardar_saldo_inicial(db: Session, anio: int, mes: int, saldo_caja_chica, saldo_banco, usuario_nombre: str) -> SaldoInicialMensual:
    """Crea o actualiza (upsert) el saldo inicial de un mes. No hace commit;
    quien llama decide cuándo guardar."""
    fila = obtener_saldo_inicial(db, anio, mes)
    if not fila:
        fila = SaldoInicialMensual(anio=anio, mes=mes)
        db.add(fila)
    fila.saldo_inicial_caja_chica = to_decimal(saldo_caja_chica).quantize(Decimal("0.01"))
    fila.saldo_inicial_banco = to_decimal(saldo_banco).quantize(Decimal("0.01"))
    fila.usuario_nombre = usuario_nombre
    fila.actualizado_en = datetime.utcnow()
    return fila


def _rango_mes(anio: int, mes: int, hasta: datetime | None = None):
    """Del 1 del mes a `hasta` (por defecto, ahora mismo si es el mes en
    curso, o el final de ese mes si es un mes pasado)."""
    inicio = datetime(anio, mes, 1)
    if hasta is not None:
        fin = hasta
    else:
        anio_actual, mes_actual_ = mes_actual()
        if (anio, mes) == (anio_actual, mes_actual_):
            fin = datetime.utcnow()
        else:
            if mes == 12:
                fin = datetime(anio + 1, 1, 1)
            else:
                fin = datetime(anio, mes + 1, 1)
    return inicio, fin


def _suma(db: Session, tipo: str, cuenta: str, desde: datetime, hasta: datetime) -> Decimal:
    total = db.query(func.coalesce(func.sum(MovimientoFinanciero.monto), 0)).filter(
        MovimientoFinanciero.tipo == tipo,
        MovimientoFinanciero.cuenta == cuenta,
        MovimientoFinanciero.fecha >= desde,
        MovimientoFinanciero.fecha < hasta,
    ).scalar()
    return to_decimal(total)


def calcular_liquidez(db: Session, anio: int | None = None, mes: int | None = None) -> dict:
    """Saldo actual de Caja Chica, de Banco, y la Liquidez Total (la suma de
    ambas), a partir del saldo con que arrancó el mes más lo que ha entrado y
    salido de cada cuenta desde entonces."""
    if anio is None or mes is None:
        anio, mes = mes_actual()
    desde, hasta = _rango_mes(anio, mes)

    fila_saldo = obtener_saldo_inicial(db, anio, mes)
    saldo_inicial_caja_chica = to_decimal(fila_saldo.saldo_inicial_caja_chica) if fila_saldo else Decimal("0.00")
    saldo_inicial_banco = to_decimal(fila_saldo.saldo_inicial_banco) if fila_saldo else Decimal("0.00")

    ingresos_caja_chica = _suma(db, "ingreso", CUENTA_CAJA_CHICA, desde, hasta)
    egresos_caja_chica = _suma(db, "gasto", CUENTA_CAJA_CHICA, desde, hasta)
    ingresos_banco = _suma(db, "ingreso", CUENTA_BANCO, desde, hasta)
    egresos_banco = _suma(db, "gasto", CUENTA_BANCO, desde, hasta)

    caja_chica_actual = (saldo_inicial_caja_chica + ingresos_caja_chica - egresos_caja_chica).quantize(Decimal("0.01"))
    banco_actual = (saldo_inicial_banco + ingresos_banco - egresos_banco).quantize(Decimal("0.01"))
    liquidez_total = (caja_chica_actual + banco_actual).quantize(Decimal("0.01"))

    return {
        "anio": anio, "mes": mes,
        "tiene_saldo_configurado": fila_saldo is not None,
        "saldo_inicial_caja_chica": saldo_inicial_caja_chica,
        "saldo_inicial_banco": saldo_inicial_banco,
        "ingresos_caja_chica": ingresos_caja_chica,
        "egresos_caja_chica": egresos_caja_chica,
        "ingresos_banco": ingresos_banco,
        "egresos_banco": egresos_banco,
        "caja_chica_actual": caja_chica_actual,
        "banco_actual": banco_actual,
        "liquidez_total": liquidez_total,
    }


def calcular_utilidad_neta(db: Session, fecha_desde: datetime, fecha_hasta: datetime) -> dict:
    """Estado de resultados simple del período: Utilidad Neta = ingresos -
    egresos, sin importar la cuenta (caja chica o banco) ni los saldos
    iniciales — es rentabilidad del negocio, no efectivo disponible."""
    ingresos = db.query(func.coalesce(func.sum(MovimientoFinanciero.monto), 0)).filter(
        MovimientoFinanciero.tipo == "ingreso",
        MovimientoFinanciero.fecha >= fecha_desde, MovimientoFinanciero.fecha <= fecha_hasta,
    ).scalar()
    egresos = db.query(func.coalesce(func.sum(MovimientoFinanciero.monto), 0)).filter(
        MovimientoFinanciero.tipo == "gasto",
        MovimientoFinanciero.fecha >= fecha_desde, MovimientoFinanciero.fecha <= fecha_hasta,
    ).scalar()
    ingresos = to_decimal(ingresos)
    egresos = to_decimal(egresos)
    utilidad = (ingresos - egresos).quantize(Decimal("0.01"))
    margen_pct = float((utilidad / ingresos * 100).quantize(Decimal("0.1"))) if ingresos > 0 else 0.0
    return {"ingresos": ingresos, "egresos": egresos, "utilidad_neta": utilidad, "margen_pct": margen_pct}


def calcular_cierre_dia(db: Session, dia: date | None = None) -> dict:
    """Reporte de cierre/arqueo diario de la Vista Cajera: desglosa lo
    cobrado hoy por método de pago. Solo incluye movimientos que vinieron
    del flujo "Registrar cobro" (metodo_pago IS NOT NULL)."""
    if dia is None:
        dia = date.today()
    desde = datetime(dia.year, dia.month, dia.day)
    hasta = datetime.combine(dia, datetime.max.time())

    movimientos = db.query(MovimientoFinanciero).filter(
        MovimientoFinanciero.metodo_pago.isnot(None),
        MovimientoFinanciero.fecha >= desde, MovimientoFinanciero.fecha <= hasta,
    ).order_by(MovimientoFinanciero.fecha.asc()).all()

    total_efectivo = sum((to_decimal(m.monto) for m in movimientos if m.metodo_pago == "Efectivo"), Decimal("0.00"))
    total_transferencia = sum((to_decimal(m.monto) for m in movimientos if m.metodo_pago == "Transferencia"), Decimal("0.00"))
    total_pos = sum((to_decimal(m.monto) for m in movimientos if m.metodo_pago == "Tarjeta (POS)"), Decimal("0.00"))
    transferencias = [m for m in movimientos if m.metodo_pago == "Transferencia"]

    return {
        "dia": dia,
        "movimientos": movimientos,
        "total_efectivo": total_efectivo,
        "total_transferencia": total_transferencia,
        "total_pos": total_pos,
        "total_dia": (total_efectivo + total_transferencia + total_pos).quantize(Decimal("0.01")),
        "transferencias": transferencias,
    }
