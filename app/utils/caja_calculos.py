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
from datetime import datetime, date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import func, or_

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


def guardar_saldo_inicial_caja_chica(db: Session, anio: int, mes: int, saldo_caja_chica, usuario_nombre: str) -> SaldoInicialMensual:
    """Igual que guardar_saldo_inicial(), pero solo toca el saldo de Caja
    Chica — el saldo de Banco queda exactamente como estaba (o en 0 si el
    mes no tenía fila todavía). La usa la Cajera desde /caja/registrar, que
    no puede ver ni tocar el saldo de Banco (eso sigue siendo solo del
    Administrador, desde /caja/panel). No hace commit."""
    fila = obtener_saldo_inicial(db, anio, mes)
    if not fila:
        fila = SaldoInicialMensual(anio=anio, mes=mes, saldo_inicial_banco=Decimal("0.00"))
        db.add(fila)
    fila.saldo_inicial_caja_chica = to_decimal(saldo_caja_chica).quantize(Decimal("0.01"))
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
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
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
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ).scalar()
    egresos = db.query(func.coalesce(func.sum(MovimientoFinanciero.monto), 0)).filter(
        MovimientoFinanciero.tipo == "gasto",
        MovimientoFinanciero.fecha >= fecha_desde, MovimientoFinanciero.fecha <= fecha_hasta,
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ).scalar()
    ingresos = to_decimal(ingresos)
    egresos = to_decimal(egresos)
    utilidad = (ingresos - egresos).quantize(Decimal("0.01"))
    margen_pct = float((utilidad / ingresos * 100).quantize(Decimal("0.1"))) if ingresos > 0 else 0.0
    return {"ingresos": ingresos, "egresos": egresos, "utilidad_neta": utilidad, "margen_pct": margen_pct}


def calcular_cierre_dia(db: Session, dia: date | None = None) -> dict:
    """Reporte de cierre/arqueo diario de la Vista Cajera.

    Incluye TODO lo que afecta la Caja Chica (efectivo físico) de hoy, venga
    de donde venga: los cobros que registra la Cajera, pero también los
    abonos y ventas de servicios/repuestos de las Órdenes, las ventas del
    Punto de Venta, y las Salidas de Caja / Crédito por Garantía — todo lo
    que ya trae `cuenta="caja_chica"` (ver MovimientoFinanciero). Las
    Transferencias y cobros con Tarjeta (POS) se muestran aparte, como
    referencia, porque esos van a Banco y no al efectivo físico que se
    cuadra aquí."""
    if dia is None:
        dia = date.today()
    desde = datetime(dia.year, dia.month, dia.day)
    hasta = datetime.combine(dia, datetime.max.time())

    ingresos_caja_chica = db.query(MovimientoFinanciero).filter(
        MovimientoFinanciero.cuenta == CUENTA_CAJA_CHICA, MovimientoFinanciero.tipo == "ingreso",
        MovimientoFinanciero.fecha >= desde, MovimientoFinanciero.fecha <= hasta,
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ).order_by(MovimientoFinanciero.fecha.asc()).all()
    egresos_caja_chica = db.query(MovimientoFinanciero).filter(
        MovimientoFinanciero.cuenta == CUENTA_CAJA_CHICA, MovimientoFinanciero.tipo == "gasto",
        MovimientoFinanciero.fecha >= desde, MovimientoFinanciero.fecha <= hasta,
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ).order_by(MovimientoFinanciero.fecha.asc()).all()

    transferencias = db.query(MovimientoFinanciero).filter(
        MovimientoFinanciero.metodo_pago == "Transferencia",
        MovimientoFinanciero.fecha >= desde, MovimientoFinanciero.fecha <= hasta,
    ).order_by(MovimientoFinanciero.fecha.asc()).all()
    cobros_pos = db.query(MovimientoFinanciero).filter(
        # "Tarjeta (POS)" es el texto que usa Caja; "Tarjeta" es el que usan
        # Órdenes/POS/Facturas (ver FORMAS_PAGO) -- un cobro con tarjeta
        # puede traer cualquiera de los dos según de dónde vino.
        MovimientoFinanciero.metodo_pago.in_(["Tarjeta (POS)", "Tarjeta"]),
        MovimientoFinanciero.fecha >= desde, MovimientoFinanciero.fecha <= hasta,
    ).order_by(MovimientoFinanciero.fecha.asc()).all()

    def _agrupar_por_categoria(movs):
        agrupado = {}
        for m in movs:
            agrupado[m.categoria] = agrupado.get(m.categoria, Decimal("0.00")) + to_decimal(m.monto)
        # de mayor a menor monto, para que lo más relevante salga primero
        return sorted(agrupado.items(), key=lambda par: par[1], reverse=True)

    total_ingresos = sum((to_decimal(m.monto) for m in ingresos_caja_chica), Decimal("0.00"))
    total_egresos = sum((to_decimal(m.monto) for m in egresos_caja_chica), Decimal("0.00"))
    total_transferencia = sum((to_decimal(m.monto) for m in transferencias), Decimal("0.00"))
    total_pos = sum((to_decimal(m.monto) for m in cobros_pos), Decimal("0.00"))

    return {
        "dia": dia,
        "ingresos_caja_chica": ingresos_caja_chica,
        "egresos_caja_chica": egresos_caja_chica,
        "ingresos_por_categoria": _agrupar_por_categoria(ingresos_caja_chica),
        "egresos_por_categoria": _agrupar_por_categoria(egresos_caja_chica),
        "total_ingresos": total_ingresos,
        "total_egresos": total_egresos,
        "total_efectivo": total_ingresos,  # alias: todo ingreso de caja chica ES efectivo físico
        "saldo_neto_dia": (total_ingresos - total_egresos).quantize(Decimal("0.01")),
        "transferencias": transferencias,
        "cobros_pos": cobros_pos,
        "total_transferencia": total_transferencia,
        "total_pos": total_pos,
        "total_dia": (total_ingresos + total_transferencia + total_pos).quantize(Decimal("0.01")),
    }


def calcular_saldo_caja_chica_a_fecha(db: Session, fecha: date) -> dict:
    """Saldo de Caja Chica (efectivo físico) al CIERRE de un día cualquiera,
    no solo hoy: el saldo inicial configurado para el mes de esa fecha, más
    todo lo que entró y salió de caja chica desde el día 1 de ese mes hasta
    el final de ese día (inclusive).

    Esto es lo que permite "apertura y cierre con fechas personalizadas"
    sin guardar una apertura/cierre distinta por cada día: en vez de un
    registro aparte, el saldo de cualquier fecha pasada se calcula al
    momento a partir del mismo libro de movimientos."""
    anio, mes = fecha.year, fecha.month
    desde = datetime(anio, mes, 1)
    hasta = datetime.combine(fecha, datetime.max.time())

    fila_saldo = obtener_saldo_inicial(db, anio, mes)
    saldo_inicial = to_decimal(fila_saldo.saldo_inicial_caja_chica) if fila_saldo else Decimal("0.00")

    ingresos = db.query(func.coalesce(func.sum(MovimientoFinanciero.monto), 0)).filter(
        MovimientoFinanciero.tipo == "ingreso", MovimientoFinanciero.cuenta == CUENTA_CAJA_CHICA,
        MovimientoFinanciero.fecha >= desde, MovimientoFinanciero.fecha <= hasta,
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ).scalar()
    egresos = db.query(func.coalesce(func.sum(MovimientoFinanciero.monto), 0)).filter(
        MovimientoFinanciero.tipo == "gasto", MovimientoFinanciero.cuenta == CUENTA_CAJA_CHICA,
        MovimientoFinanciero.fecha >= desde, MovimientoFinanciero.fecha <= hasta,
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ).scalar()
    ingresos = to_decimal(ingresos)
    egresos = to_decimal(egresos)
    saldo_en_caja = (saldo_inicial + ingresos - egresos).quantize(Decimal("0.01"))

    return {
        "fecha": fecha,
        "saldo_inicial_mes": saldo_inicial,
        "ingresos_acumulados_mes": ingresos,
        "egresos_acumulados_mes": egresos,
        "saldo_en_caja": saldo_en_caja,
    }


def calcular_resumen_caja_chica(db: Session, desde: datetime, hasta: datetime, buscar: str = "") -> dict:
    """Resumen de Caja Chica (ingresos/egresos con desglose por categoría)
    para cualquier rango de fechas — la versión "por mes o por rango" de lo
    que calcular_cierre_dia() ya hace para un solo día. Esto es lo que ve
    la Cajera en "Reportes de Caja": nunca incluye banco ni liquidez. Si se
    pasa `buscar`, filtra por categoría/descripción/referencia/cliente (útil
    para encontrar un movimiento específico, por ejemplo el de una orden ya
    eliminada, y poder corregirlo)."""
    filtro_base = [
        MovimientoFinanciero.cuenta == CUENTA_CAJA_CHICA, MovimientoFinanciero.fecha >= desde, MovimientoFinanciero.fecha <= hasta,
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ]
    filtros_busqueda = []
    if buscar.strip():
        like = f"%{buscar.strip()}%"
        filtros_busqueda = [or_(
            MovimientoFinanciero.categoria.ilike(like), MovimientoFinanciero.descripcion.ilike(like),
            MovimientoFinanciero.referencia.ilike(like), MovimientoFinanciero.cliente_nombre.ilike(like),
        )]

    ingresos = db.query(MovimientoFinanciero).filter(
        *filtro_base, MovimientoFinanciero.tipo == "ingreso", *filtros_busqueda,
    ).order_by(MovimientoFinanciero.fecha.desc()).all()
    egresos = db.query(MovimientoFinanciero).filter(
        *filtro_base, MovimientoFinanciero.tipo == "gasto", *filtros_busqueda,
    ).order_by(MovimientoFinanciero.fecha.desc()).all()

    def _agrupar_por_categoria(movs):
        agrupado = {}
        for m in movs:
            agrupado[m.categoria] = agrupado.get(m.categoria, Decimal("0.00")) + to_decimal(m.monto)
        return sorted(agrupado.items(), key=lambda par: par[1], reverse=True)

    total_ingresos = sum((to_decimal(m.monto) for m in ingresos), Decimal("0.00"))
    total_egresos = sum((to_decimal(m.monto) for m in egresos), Decimal("0.00"))

    return {
        "desde": desde, "hasta": hasta,
        "ingresos": ingresos, "egresos": egresos,
        "ingresos_por_categoria": _agrupar_por_categoria(ingresos),
        "egresos_por_categoria": _agrupar_por_categoria(egresos),
        "total_ingresos": total_ingresos, "total_egresos": total_egresos,
        "neto": (total_ingresos - total_egresos).quantize(Decimal("0.01")),
        "movimientos": sorted((*ingresos, *egresos), key=lambda m: m.fecha, reverse=True),
    }


def calcular_saldo_anterior(db: Session, fecha: date) -> Decimal:
    """Saldo en Caja Chica al cierre del día ANTERIOR a `fecha` — el "Saldo
    Anterior" de la hoja de cálculo original que se arrastra día a día. Si
    `fecha` es el día 1 de un mes, no hay un día anterior dentro del mismo
    mes que calcular: se usa directamente el saldo inicial configurado para
    ese mes."""
    if fecha.day == 1:
        fila_saldo = obtener_saldo_inicial(db, fecha.year, fecha.month)
        return to_decimal(fila_saldo.saldo_inicial_caja_chica) if fila_saldo else Decimal("0.00")
    dia_anterior = fecha - timedelta(days=1)
    return calcular_saldo_caja_chica_a_fecha(db, dia_anterior)["saldo_en_caja"]
