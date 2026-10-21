"""Apertura y cierre de caja (turnos): reglas y cálculos.

Qué hace este módulo:
  * Vincula sola, a la caja abierta, cada abono (Pago), movimiento de dinero
    (MovimientoFinanciero), venta (Venta) y factura (Factura) NUEVOS que se
    registren mientras haya una caja abierta (ver _vincular_a_turno_abierto).
    Lo anterior a este módulo queda sin turno y no se toca.
  * Decide si una operación de dinero está permitida (verificar_caja): a
    partir de Configuracion.caja_obligatoria_desde, cobrar, abonar, facturar
    y vender en el POS requieren una caja abierta HOY.
  * Calcula el arqueo de un turno (calcular_resumen_turno).

No modifica el registro contable: Liquidez, Contabilidad, Reportes y el
Libro Diario se siguen calculando exactamente igual que antes.
"""
from datetime import datetime, date, time, timezone
from decimal import Decimal

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import (
    TurnoCaja, Configuracion, MovimientoFinanciero, Pago, Venta, Factura,
    HN_TZ, TURNO_ABIERTO, CATEGORIA_VENTA_FACTURADA, CATEGORIA_DEPOSITO_BANCO,
)
from app.utils.calculations import to_decimal

CUENTA_CAJA_CHICA = "caja_chica"
CERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# Hora de Honduras (la base de datos guarda todo en UTC)
# ---------------------------------------------------------------------------
def a_hora_local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(HN_TZ)


def fecha_local(dt: datetime) -> date:
    return a_hora_local(dt).date()


def hoy_local() -> date:
    return datetime.now(HN_TZ).date()


def inicio_dia_local_en_utc(dia: date) -> datetime:
    """00:00 de `dia` en Honduras, expresado como datetime UTC sin zona
    (como se guarda en la base de datos)."""
    return datetime.combine(dia, time.min, tzinfo=HN_TZ).astimezone(timezone.utc).replace(tzinfo=None)


def local_a_utc(dt_local: datetime) -> datetime:
    """Datetime ingresado en hora de Honduras (sin zona) -> UTC sin zona."""
    return dt_local.replace(tzinfo=HN_TZ).astimezone(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Estado de la caja
# ---------------------------------------------------------------------------
def turno_abierto(db: Session) -> TurnoCaja | None:
    return (
        db.query(TurnoCaja)
        .filter(TurnoCaja.estado == TURNO_ABIERTO)
        .order_by(TurnoCaja.id.desc())
        .first()
    )


def caja_obligatoria_activa(db: Session) -> bool:
    cfg = db.get(Configuracion, 1)
    desde = cfg.caja_obligatoria_desde if cfg else None
    return bool(desde) and datetime.utcnow() >= desde


def es_turno_de_dia_anterior(turno: TurnoCaja) -> bool:
    return fecha_local(turno.fecha_apertura) < hoy_local()


def verificar_caja(db: Session) -> str | None:
    """None si se puede registrar dinero; si no, el mensaje que explica por
    qué no (para mostrarlo tal cual al usuario)."""
    if not caja_obligatoria_activa(db):
        return None
    turno = turno_abierto(db)
    if turno is None:
        return (
            "La caja está cerrada. Para registrar cobros, abonos, facturas o ventas "
            "primero hay que abrir la caja en «Apertura y cierre»."
        )
    if es_turno_de_dia_anterior(turno):
        return (
            f"La caja del {fecha_local(turno.fecha_apertura).strftime('%d/%m/%Y')} sigue abierta. "
            "Ciérrala primero en «Apertura y cierre» y luego abre la de hoy."
        )
    return None


# ---------------------------------------------------------------------------
# Vinculación automática de los registros nuevos al turno abierto
# ---------------------------------------------------------------------------
_MODELOS_DEL_TURNO = (MovimientoFinanciero, Pago, Venta, Factura)


def _vincular_a_turno_abierto(session, flush_context, instances):
    nuevos = [
        obj for obj in session.new
        if isinstance(obj, _MODELOS_DEL_TURNO) and getattr(obj, "turno_caja_id", None) is None
    ]
    if not nuevos:
        return
    with session.no_autoflush:
        turno_id = (
            session.query(TurnoCaja.id)
            .filter(TurnoCaja.estado == TURNO_ABIERTO)
            .order_by(TurnoCaja.id.desc())
            .limit(1)
            .scalar()
        )
    if turno_id is None:
        return
    for obj in nuevos:
        obj.turno_caja_id = turno_id


def registrar_vinculacion_automatica() -> None:
    if not event.contains(Session, "before_flush", _vincular_a_turno_abierto):
        event.listen(Session, "before_flush", _vincular_a_turno_abierto)


# ---------------------------------------------------------------------------
# Arqueo / resumen de un turno
# ---------------------------------------------------------------------------
def _metodo_normalizado(metodo: str | None, cuenta: str | None = None) -> str:
    if metodo in ("Tarjeta (POS)", "Tarjeta"):
        return "Tarjeta"
    if metodo:
        return metodo
    return "Efectivo" if cuenta == CUENTA_CAJA_CHICA else "Otro"


def calcular_resumen_turno(db: Session, turno: TurnoCaja) -> dict:
    """Arqueo de un turno.

    Efectivo esperado = efectivo inicial
                        + abonos/pagos de órdenes en Efectivo
                        + otros ingresos de Caja Chica (cobros de Caja,
                          ventas del POS en efectivo, otros ingresos)
                        - salidas de Caja Chica (gastos, depósitos al banco...)

    Los ingresos que genera una Factura de orden NO se suman aquí: ese
    dinero ya se contó cuando se recibió el abono/pago de la orden (sumarlo
    otra vez lo duplicaría)."""
    movimientos = (
        db.query(MovimientoFinanciero)
        .filter(MovimientoFinanciero.turno_caja_id == turno.id)
        .order_by(MovimientoFinanciero.fecha.asc())
        .all()
    )
    pagos = (
        db.query(Pago).filter(Pago.turno_caja_id == turno.id, Pago.anulado == False).order_by(Pago.fecha.asc()).all()  # noqa: E712
    )
    ventas_pos = (
        db.query(Venta)
        .filter(Venta.turno_caja_id == turno.id, Venta.orden_id.is_(None), Venta.anulada == False)  # noqa: E712
        .order_by(Venta.fecha.asc())
        .all()
    )
    facturas = (
        db.query(Factura).filter(Factura.turno_caja_id == turno.id).order_by(Factura.fecha_emision.asc()).all()
    )

    validos = [m for m in movimientos if not m.excluir_de_contabilidad]
    ingresos_efectivo = [
        m for m in validos
        if m.tipo == "ingreso" and m.cuenta == CUENTA_CAJA_CHICA and m.categoria != CATEGORIA_VENTA_FACTURADA
    ]
    salidas_efectivo = [m for m in validos if m.tipo == "gasto" and m.cuenta == CUENTA_CAJA_CHICA]
    pagos_efectivo = [p for p in pagos if (p.forma_pago or "Efectivo") == "Efectivo"]

    total_pagos_efectivo = sum((to_decimal(p.monto) for p in pagos_efectivo), CERO)
    total_ingresos_efectivo = sum((to_decimal(m.monto) for m in ingresos_efectivo), CERO)
    total_salidas_efectivo = sum((to_decimal(m.monto) for m in salidas_efectivo), CERO)
    monto_inicial = to_decimal(turno.monto_inicial or 0)
    efectivo_esperado = (
        monto_inicial + total_pagos_efectivo + total_ingresos_efectivo - total_salidas_efectivo
    ).quantize(Decimal("0.01"))

    # Cobrado en el turno, por forma de pago (solo dinero que entró: abonos
    # de órdenes y cobros/ventas; no las facturas, que ya están contadas en
    # sus abonos, ni la entrada a Banco de un depósito, que es un traslado).
    cobrado_por_metodo: dict[str, Decimal] = {}
    for p in pagos:
        clave = _metodo_normalizado(p.forma_pago or "Efectivo")
        cobrado_por_metodo[clave] = cobrado_por_metodo.get(clave, CERO) + to_decimal(p.monto)
    for m in validos:
        if m.tipo != "ingreso" or m.categoria in (CATEGORIA_VENTA_FACTURADA, CATEGORIA_DEPOSITO_BANCO):
            continue
        clave = _metodo_normalizado(m.metodo_pago, m.cuenta)
        cobrado_por_metodo[clave] = cobrado_por_metodo.get(clave, CERO) + to_decimal(m.monto)
    orden_metodos = ["Efectivo", "Transferencia", "Tarjeta", "Otro"]
    cobrado_por_metodo_lista = sorted(
        cobrado_por_metodo.items(),
        key=lambda par: orden_metodos.index(par[0]) if par[0] in orden_metodos else len(orden_metodos),
    )
    total_cobrado = sum(cobrado_por_metodo.values(), CERO)

    return {
        "monto_inicial": monto_inicial,
        "pagos": pagos,
        "pagos_efectivo": pagos_efectivo,
        "total_pagos_efectivo": total_pagos_efectivo,
        "movimientos": movimientos,
        "ingresos_efectivo": ingresos_efectivo,
        "total_ingresos_efectivo": total_ingresos_efectivo,
        "salidas_efectivo": salidas_efectivo,
        "total_salidas_efectivo": total_salidas_efectivo,
        "efectivo_esperado": efectivo_esperado,
        "ventas_pos": ventas_pos,
        "total_ventas_pos": sum((to_decimal(v.total) for v in ventas_pos), CERO),
        "facturas": facturas,
        "total_facturado": sum((to_decimal(f.total) for f in facturas if not f.anulada), CERO),
        "cobrado_por_metodo": cobrado_por_metodo_lista,
        "total_cobrado": total_cobrado,
    }


def ultimo_efectivo_contado(db: Session) -> Decimal | None:
    """Efectivo que quedó contado en el último cierre (sugerencia para el
    efectivo inicial de la siguiente apertura)."""
    ultimo = (
        db.query(TurnoCaja)
        .filter(TurnoCaja.estado != TURNO_ABIERTO, TurnoCaja.efectivo_contado.isnot(None))
        .order_by(TurnoCaja.fecha_cierre.desc())
        .first()
    )
    return to_decimal(ultimo.efectivo_contado) if ultimo else None


# ---------------------------------------------------------------------------
# Para la plantilla base (aviso en todas las páginas)
# ---------------------------------------------------------------------------
def estado_caja_para_plantilla() -> dict:
    """Nunca lanza error: si algo falla devuelve un estado neutro, para que
    un problema aquí no tumbe ninguna página del sistema."""
    from app.database import SessionLocal
    vacio = {"obligatoria": False, "bloqueado": False, "mensaje": None, "turno": None, "obligatoria_desde": None}
    try:
        db = SessionLocal()
        try:
            cfg = db.get(Configuracion, 1)
            turno = turno_abierto(db)
            mensaje = verificar_caja(db)
            return {
                "obligatoria": caja_obligatoria_activa(db),
                "obligatoria_desde": a_hora_local(cfg.caja_obligatoria_desde) if cfg and cfg.caja_obligatoria_desde else None,
                "bloqueado": mensaje is not None,
                "mensaje": mensaje,
                "turno": {"id": turno.id} if turno else None,
                "turno_abierto_desde": a_hora_local(turno.fecha_apertura) if turno else None,
            }
        finally:
            db.close()
    except Exception:
        return vacio


# ---------------------------------------------------------------------------
# Lo de cada día (para ver primero el cierre del día y después lo general)
# ---------------------------------------------------------------------------
def _bloque_dia(dia: date) -> dict:
    return {
        "dia": dia, "cobrado_por_metodo": {}, "total_cobrado": CERO,
        "entradas_efectivo": CERO, "salidas_efectivo": CERO,
        "abonos": 0, "ventas_pos": 0, "total_ventas_pos": CERO,
        "facturas": 0, "total_facturado": CERO,
    }


def resumen_por_dia(resumen: dict, incluir_dia: date | None = None) -> list[dict]:
    """Agrupa por día (hora de Honduras) lo que ya calculó
    calcular_resumen_turno: lo cobrado por forma de pago, las entradas y
    salidas de efectivo, ventas del POS y facturas. Del día más reciente al
    más antiguo. `incluir_dia` agrega ese día aunque todavía no tenga nada
    (por ejemplo "hoy", con la caja recién abierta)."""
    dias: dict[date, dict] = {}
    if incluir_dia is not None:
        dias[incluir_dia] = _bloque_dia(incluir_dia)

    def bloque(dt):
        d = fecha_local(dt)
        if d not in dias:
            dias[d] = _bloque_dia(d)
        return dias[d]

    def sumar_cobro(b, metodo, monto):
        b["cobrado_por_metodo"][metodo] = b["cobrado_por_metodo"].get(metodo, CERO) + monto
        b["total_cobrado"] += monto

    ids_pagos_efectivo = {p.id for p in resumen["pagos_efectivo"]}
    ids_ingresos_efectivo = {m.id for m in resumen["ingresos_efectivo"]}
    ids_salidas_efectivo = {m.id for m in resumen["salidas_efectivo"]}

    for p in resumen["pagos"]:
        b = bloque(p.fecha)
        monto = to_decimal(p.monto)
        sumar_cobro(b, _metodo_normalizado(p.forma_pago or "Efectivo"), monto)
        b["abonos"] += 1
        if p.id in ids_pagos_efectivo:
            b["entradas_efectivo"] += monto
    for m in resumen["movimientos"]:
        if m.excluir_de_contabilidad:
            continue
        b = bloque(m.fecha)
        monto = to_decimal(m.monto)
        if m.tipo == "ingreso" and m.categoria not in (CATEGORIA_VENTA_FACTURADA, CATEGORIA_DEPOSITO_BANCO):
            sumar_cobro(b, _metodo_normalizado(m.metodo_pago, m.cuenta), monto)
        if m.id in ids_ingresos_efectivo:
            b["entradas_efectivo"] += monto
        if m.id in ids_salidas_efectivo:
            b["salidas_efectivo"] += monto
    for v in resumen["ventas_pos"]:
        b = bloque(v.fecha)
        b["ventas_pos"] += 1
        b["total_ventas_pos"] += to_decimal(v.total)
    for f in resumen["facturas"]:
        b = bloque(f.fecha_emision)
        if not f.anulada:
            b["facturas"] += 1
            b["total_facturado"] += to_decimal(f.total)

    orden_metodos = ["Efectivo", "Transferencia", "Tarjeta", "Otro"]
    resultado = []
    for d in sorted(dias, reverse=True):
        b = dias[d]
        b["cobrado_por_metodo"] = sorted(
            b["cobrado_por_metodo"].items(),
            key=lambda par: orden_metodos.index(par[0]) if par[0] in orden_metodos else len(orden_metodos),
        )
        b["neto_efectivo"] = (b["entradas_efectivo"] - b["salidas_efectivo"]).quantize(Decimal("0.01"))
        resultado.append(b)
    return resultado
