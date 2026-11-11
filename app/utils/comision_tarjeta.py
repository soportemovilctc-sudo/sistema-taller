"""Comisión del POS en los cobros con tarjeta.

El banco no deposita completo lo que se cobra con tarjeta: descuenta un
porcentaje (3.8%). Para que el banco del sistema cuadre con el real, cada
cobro con tarjeta que entra al banco genera sola una salida del banco
«Comisiones POS / tarjeta» por ese porcentaje.

* La cajera no ve nada distinto: el cobro sigue siendo por el total (su
  caja y su cierre no cambian) y la comisión no queda en su caja.
* Solo aplica a cobros con fecha desde ConfiguracionFacturacion.
  comision_tarjeta_desde (lo anterior queda como estaba).
* Si el cobro se anula, se borra o se corrige (monto, forma de pago, banco),
  la comisión se anula o se corrige sola, con su asiento contable.

Todo ocurre en un listener before_flush, así funciona en cualquier pantalla
que registre un cobro con tarjeta (órdenes, Punto de Venta, Caja, CxC...).
"""
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models import (
    MovimientoFinanciero, ConfiguracionFacturacion, AsientoContable, DetalleAsiento, CuentaContable,
    CATEGORIA_COMISION_TARJETA, CATEGORIA_DEPOSITO_BANCO, CATEGORIA_SALDO_INICIAL_BANCO,
)

CENT = Decimal("0.01")
CTA_BANCO = "1102"
CTA_EGRESOS = "5101"
_CAMPOS = ("monto", "metodo_pago", "cuenta", "banco_id", "excluir_de_contabilidad", "fecha", "tipo")


def _config(session, cache):
    if "cfg" not in cache:
        cfg = session.get(ConfiguracionFacturacion, 1)
        pct = Decimal(str(cfg.comision_tarjeta_pct)) if cfg and cfg.comision_tarjeta_pct is not None else Decimal("0")
        cache["cfg"] = (pct, cfg.comision_tarjeta_desde if cfg else None)
    return cache["cfg"]


def _es_cobro_con_tarjeta(m: MovimientoFinanciero) -> bool:
    return (
        m.tipo == "ingreso" and m.cuenta == "banco" and "tarjeta" in (m.metodo_pago or "").lower()
        and not m.excluir_de_contabilidad
        and m.categoria not in (CATEGORIA_COMISION_TARJETA, CATEGORIA_DEPOSITO_BANCO, CATEGORIA_SALDO_INICIAL_BANCO)
    )


def _aplica(session, cache, m: MovimientoFinanciero) -> bool:
    pct, desde = _config(session, cache)
    if pct <= 0 or desde is None or not _es_cobro_con_tarjeta(m):
        return False
    return (m.fecha or datetime.utcnow()) >= desde


def _monto_comision(session, cache, m) -> Decimal:
    pct, _ = _config(session, cache)
    return (Decimal(str(m.monto)) * pct / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)


def _siguiente_asiento(session, cache) -> str:
    """Siguiente número AC-xxxxxx contando también los asientos que todavía
    no se han guardado en este mismo flush."""
    if "n_asiento" not in cache:
        nums = [0]
        ultimo = session.query(AsientoContable.numero_asiento).order_by(AsientoContable.id.desc()).limit(1).scalar()
        for texto in [ultimo] + [a.numero_asiento for a in session.new if isinstance(a, AsientoContable)]:
            mt = re.search(r"(\d+)\s*$", texto or "")
            if mt:
                nums.append(int(mt.group(1)))
        cache["n_asiento"] = max(nums)
    cache["n_asiento"] += 1
    return f"AC-{cache['n_asiento']:06d}"


def _cuenta_id(session, cache, codigo):
    clave = f"cta_{codigo}"
    if clave not in cache:
        cache[clave] = session.query(CuentaContable.id).filter(CuentaContable.codigo == codigo).scalar()
    return cache[clave]


def _quitar_asientos(session, comision):
    if comision.id is None:
        return
    for a in session.query(AsientoContable).filter(AsientoContable.movimiento_financiero_id == comision.id).all():
        session.delete(a)


def _poner_asiento(session, cache, comision):
    banco, egresos = _cuenta_id(session, cache, CTA_BANCO), _cuenta_id(session, cache, CTA_EGRESOS)
    if not banco or not egresos:
        return  # el Libro Diario nunca bloquea un cobro
    asiento = AsientoContable(
        numero_asiento=_siguiente_asiento(session, cache), fecha=comision.fecha or datetime.utcnow(),
        concepto=f"{CATEGORIA_COMISION_TARJETA} - {comision.descripcion or ''}"[:255], tipo_evento="comision_tarjeta",
        referencia=comision.referencia or "", usuario_nombre=comision.usuario_nombre,
    )
    asiento.movimiento = comision
    asiento.detalles = [DetalleAsiento(cuenta_id=egresos, debe=comision.monto, haber=0),
                        DetalleAsiento(cuenta_id=banco, debe=0, haber=comision.monto)]
    session.add(asiento)


def _llenar(session, cache, comision, fuente):
    pct, _ = _config(session, cache)
    comision.monto = _monto_comision(session, cache, fuente)
    comision.fecha = fuente.fecha or datetime.utcnow()
    comision.banco_id = fuente.banco_id
    comision.referencia = fuente.referencia or ""
    comision.descripcion = (f"Comisión del {pct.normalize()}% del POS por cobro con tarjeta de L {Decimal(str(fuente.monto)):,.2f}"
                            + (f" · {fuente.referencia}" if fuente.referencia else ""))


def _crear(session, cache, fuente):
    comision = MovimientoFinanciero(
        tipo="gasto", categoria=CATEGORIA_COMISION_TARJETA, cuenta="banco", metodo_pago=None,
        usuario_nombre="Sistema (comisión POS)", cliente_nombre=fuente.cliente_nombre,
    )
    _llenar(session, cache, comision, fuente)
    comision.comision_de = fuente
    session.add(comision)
    _poner_asiento(session, cache, comision)


def _comisiones_de(session, fuente):
    if fuente.id is None:
        return []
    return session.query(MovimientoFinanciero).filter(MovimientoFinanciero.comision_de_id == fuente.id).all()


def _cambio_relevante(m) -> bool:
    estado = inspect(m)
    return any(estado.attrs[c].history.has_changes() for c in _CAMPOS)


def _sincronizar(session, flush_context, instances):
    cache = {}
    with session.no_autoflush:
        for m in list(session.new):
            if isinstance(m, MovimientoFinanciero) and m.categoria != CATEGORIA_COMISION_TARJETA and _aplica(session, cache, m):
                _crear(session, cache, m)

        for m in list(session.dirty):
            if not isinstance(m, MovimientoFinanciero) or m.categoria == CATEGORIA_COMISION_TARJETA:
                continue
            if not session.is_modified(m) or not _cambio_relevante(m):
                continue
            existentes = _comisiones_de(session, m)
            debe_tener = _aplica(session, cache, m)
            if not existentes:
                if debe_tener:
                    _crear(session, cache, m)
                continue
            for c in existentes:
                _quitar_asientos(session, c)
                if debe_tener:
                    c.excluir_de_contabilidad = False
                    _llenar(session, cache, c, m)
                    _poner_asiento(session, cache, c)
                else:
                    c.excluir_de_contabilidad = True

        for m in list(session.deleted):
            if isinstance(m, MovimientoFinanciero) and m.categoria != CATEGORIA_COMISION_TARJETA:
                for c in _comisiones_de(session, m):
                    _quitar_asientos(session, c)
                    session.delete(c)


_registrado = False


def registrar_comision_tarjeta() -> None:
    global _registrado
    if not _registrado:
        event.listen(Session, "before_flush", _sincronizar)
        _registrado = True
