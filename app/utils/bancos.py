"""Varios bancos.

Todo el dinero del banco sigue en la cuenta «banco» (los totales de Banco,
Liquidez, Estados financieros y el Libro Diario no cambian). Cada
movimiento del banco guarda además *a qué banco* entró o de cuál salió
(banco_id). Vacío = el banco principal (Banco Atlántida): así todo lo que
se registró antes de que hubiera varios bancos queda en Atlántida.

Saldo de un banco que no es el principal = lo que entró menos lo que salió
de ese banco (su saldo inicial también es un movimiento de entrada, que no
cuenta como venta). Saldo del principal = total del banco − los demás.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import Banco, MovimientoFinanciero
from app.utils.calculations import to_decimal

CUENTA_BANCO = "banco"
CERO = Decimal("0.00")


def q(v) -> Decimal:
    return to_decimal(v or 0).quantize(Decimal("0.01"))


def banco_principal(db: Session) -> Banco:
    b = db.query(Banco).filter(Banco.principal == True).order_by(Banco.id).first()  # noqa: E712
    if not b:
        b = db.query(Banco).order_by(Banco.id).first()
    if not b:
        b = Banco(nombre="Banco Atlántida", principal=True, activo=True)
        db.add(b)
        db.flush()
    return b


def bancos_activos(db: Session) -> list[Banco]:
    principal = banco_principal(db)
    otros = db.query(Banco).filter(Banco.activo == True, Banco.id != principal.id).order_by(Banco.nombre).all()  # noqa: E712
    return [principal] + otros


def todos_los_bancos(db: Session) -> list[Banco]:
    principal = banco_principal(db)
    otros = db.query(Banco).filter(Banco.id != principal.id).order_by(Banco.activo.desc(), Banco.nombre).all()
    return [principal] + otros


def resolver_banco_id(db: Session, valor) -> int | None:
    """Del formulario al banco_id que se guarda: un banco activo distinto
    del principal, o None (= el principal)."""
    try:
        bid = int(str(valor or "").strip())
    except ValueError:
        return None
    b = db.get(Banco, bid)
    if not b or not b.activo or b.principal:
        return None
    return b.id


def banco_si_aplica(db: Session, cuenta_o_forma: str, valor) -> int | None:
    """banco_id solo cuando el dinero va al banco (cuenta «banco» o forma de
    pago distinta de Efectivo)."""
    if cuenta_o_forma in ("caja_chica", "Efectivo", "", None):
        return None
    return resolver_banco_id(db, valor)


def filtro_banco(db: Session, banco_id: int | None):
    """Condición SQL para los movimientos de un banco (None = todos)."""
    if banco_id is None:
        return None
    principal = banco_principal(db)
    if banco_id == principal.id:
        return or_(MovimientoFinanciero.banco_id == None, MovimientoFinanciero.banco_id == principal.id)  # noqa: E711
    return MovimientoFinanciero.banco_id == banco_id


def _neto_otro(db: Session, banco_id: int, hasta: datetime) -> Decimal:
    total = CERO
    for tipo, signo in (("ingreso", 1), ("gasto", -1)):
        s = db.query(func.coalesce(func.sum(MovimientoFinanciero.monto), 0)).filter(
            MovimientoFinanciero.cuenta == CUENTA_BANCO, MovimientoFinanciero.banco_id == banco_id,
            MovimientoFinanciero.tipo == tipo, MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
            MovimientoFinanciero.fecha < hasta,
        ).scalar()
        total += signo * to_decimal(s)
    return q(total)


def saldo_banco_a(db: Session, banco_id: int | None, instante: datetime) -> Decimal:
    """Saldo de un banco (None = todos los bancos juntos) justo antes de `instante`."""
    from app.utils.estados_financieros import saldo_efectivo_a
    total = q(saldo_efectivo_a(db, instante)["banco"])
    if banco_id is None:
        return total
    principal = banco_principal(db)
    if banco_id != principal.id:
        return _neto_otro(db, banco_id, instante)
    otros = db.query(Banco.id).filter(Banco.id != principal.id).all()
    return q(total - sum((_neto_otro(db, bid, instante) for (bid,) in otros), CERO))


def saldos_por_banco(db: Session, instante: datetime) -> list[dict]:
    principal = banco_principal(db)
    filas = []
    for b in todos_los_bancos(db):
        saldo = saldo_banco_a(db, b.id, instante)
        if b.activo or saldo != 0 or b.id == principal.id:
            filas.append({"banco": b, "saldo": saldo})
    return filas


def nombre_banco(db: Session, banco_id: int | None) -> str:
    if banco_id:
        b = db.get(Banco, banco_id)
        if b:
            return b.nombre
    return banco_principal(db).nombre


def neto_otros_bancos_antes(db: Session, instante: datetime) -> Decimal:
    """Lo que tienen los bancos que no son el principal justo antes de
    `instante`. El «saldo inicial de Banco» que se configura por mes en el
    Panel gerencial es el del banco principal; a ese se le suman los demás."""
    principal = banco_principal(db)
    otros = db.query(Banco.id).filter(Banco.id != principal.id).all()
    return q(sum((_neto_otro(db, bid, instante) for (bid,) in otros), CERO))
