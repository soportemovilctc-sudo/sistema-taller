"""Cuentas por cobrar anotadas a mano: ventas al crédito y préstamos.

* Venta al crédito: al anotarla no mueve caja ni banco. Cada pago que entra
  es la venta (ingreso «Cobro de venta al crédito», con su parte de ISV si
  la venta lleva ISV).
* Préstamo: al anotarlo sale el dinero de la Caja Chica o de un banco
  («Préstamo otorgado»). Cuando lo devuelven entra («Cobro de préstamo»).
  Ninguno de los dos es venta ni egreso del negocio (ver
  CATEGORIAS_FUERA_DE_RESULTADOS); en el Balance queda como «Préstamos por
  cobrar».

Los pagos se registran en partes, en Efectivo (a la caja abierta),
Transferencia o Tarjeta (al banco elegido). Nada se borra: se anula con
motivo y deja de contar."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    CuentaPorCobrar, CxCPago, MovimientoFinanciero,
    CXC_VENTA, CXC_PRESTAMO, CXC_PENDIENTE, CXC_PAGADA, CXC_ANULADA,
    CATEGORIA_PRESTAMO_OTORGADO, CATEGORIA_COBRO_PRESTAMO, CATEGORIA_COBRO_VENTA_CREDITO,
)
from app.utils.calculations import to_decimal
from app.utils.numbering import siguiente_numero
from app.utils.libro_diario import registrar_asiento_para_movimiento, eliminar_asiento_de_movimiento
from app.utils.bancos import resolver_banco_id

CERO = Decimal("0.00")
FORMAS_PAGO_CXC = ("Efectivo", "Transferencia", "Tarjeta")
REFERENCIA_CXC = "CxC"


def q(v) -> Decimal:
    return to_decimal(v or 0).quantize(Decimal("0.01"))


def generar_numero(db: Session) -> str:
    ultimo = db.query(CuentaPorCobrar).order_by(CuentaPorCobrar.id.desc()).first()
    return siguiente_numero(ultimo.numero if ultimo else None, "CXC")


def _monto(texto) -> Decimal:
    try:
        v = q(str(texto or "").replace(",", "").replace("L", "").strip() or 0)
    except Exception:  # noqa: BLE001
        raise ValueError("Escribe un monto válido.")
    if v <= 0:
        raise ValueError("El monto debe ser mayor a cero.")
    return v


def crear(db: Session, *, tipo: str, deudor: str, cliente_id: int | None, telefono: str, concepto: str,
          monto, con_isv: bool, tasa_isv: Decimal, vence, cuenta_salida: str, banco_id_raw, usuario_nombre: str,
          fecha: datetime | None = None) -> CuentaPorCobrar:
    if tipo not in (CXC_VENTA, CXC_PRESTAMO):
        raise ValueError("Tipo no válido.")
    deudor = (deudor or "").strip()
    if not deudor:
        raise ValueError("Escribe a quién se le cobra (o elige el cliente).")
    total = _monto(monto)
    isv = CERO
    if tipo == CXC_VENTA and con_isv and tasa_isv > 0:
        isv = q(total - total / (1 + tasa_isv / Decimal(100)))
    cxc = CuentaPorCobrar(
        numero=generar_numero(db), tipo=tipo, cliente_id=cliente_id, deudor=deudor[:150], telefono=(telefono or "").strip()[:40],
        concepto=(concepto or "").strip(), monto=total, con_isv=bool(tipo == CXC_VENTA and con_isv), isv_monto=isv,
        fecha=fecha or datetime.utcnow(), vence=vence, estado=CXC_PENDIENTE, usuario_nombre=usuario_nombre,
    )
    db.add(cxc)
    db.flush()
    if tipo == CXC_PRESTAMO:
        cuenta = "banco" if cuenta_salida == "banco" else "caja_chica"
        banco_id = resolver_banco_id(db, banco_id_raw) if cuenta == "banco" else None
        mov = MovimientoFinanciero(
            tipo="gasto", categoria=CATEGORIA_PRESTAMO_OTORGADO, monto=total, fecha=cxc.fecha,
            descripcion=f"Préstamo {cxc.numero} a {cxc.deudor}" + (f" · {cxc.concepto}" if cxc.concepto else ""),
            usuario_nombre=usuario_nombre, referencia=cxc.numero, cuenta=cuenta, banco_id=banco_id,
            metodo_pago="Efectivo" if cuenta == "caja_chica" else "Transferencia", cliente_nombre=cxc.deudor,
        )
        db.add(mov)
        db.flush()
        registrar_asiento_para_movimiento(db, mov)
        cxc.cuenta_salida, cxc.banco_id, cxc.mov_salida_id = cuenta, banco_id, mov.id
    return cxc


def registrar_pago(db: Session, cxc: CuentaPorCobrar, *, monto, forma_pago: str, banco_id_raw, referencia: str,
                   usuario_nombre: str) -> CxCPago:
    if cxc.estado == CXC_ANULADA:
        raise ValueError("Esta cuenta está anulada.")
    if forma_pago not in FORMAS_PAGO_CXC:
        raise ValueError("Elige cómo pagó: Efectivo, Transferencia o Tarjeta.")
    valor = _monto(monto)
    saldo = q(cxc.saldo)
    if valor > saldo:
        raise ValueError(f"El pago (L {valor:,.2f}) es mayor que lo que falta por cobrar (L {saldo:,.2f}).")
    referencia = (referencia or "").strip()[:60]
    if forma_pago == "Transferencia" and not referencia:
        raise ValueError("Escribe el número de referencia de la transferencia.")
    efectivo = forma_pago == "Efectivo"
    banco_id = None if efectivo else resolver_banco_id(db, banco_id_raw)
    isv = q(valor * to_decimal(cxc.isv_monto) / to_decimal(cxc.monto)) if cxc.tipo == CXC_VENTA and to_decimal(cxc.isv_monto) > 0 else CERO
    categoria = CATEGORIA_COBRO_VENTA_CREDITO if cxc.tipo == CXC_VENTA else CATEGORIA_COBRO_PRESTAMO
    mov = MovimientoFinanciero(
        tipo="ingreso", categoria=categoria, monto=valor, fecha=datetime.utcnow(),
        descripcion=f"{'Pago de venta al crédito' if cxc.tipo == CXC_VENTA else 'Pago de préstamo'} {cxc.numero} · {cxc.deudor}",
        usuario_nombre=usuario_nombre, referencia=cxc.numero, cuenta="caja_chica" if efectivo else "banco",
        banco_id=banco_id, metodo_pago=forma_pago, cliente_nombre=cxc.deudor, num_referencia=referencia or None,
        estado_conciliacion="pendiente" if forma_pago == "Transferencia" else None,
    )
    db.add(mov)
    db.flush()
    pago = CxCPago(cxc_id=cxc.id, fecha=mov.fecha, monto=valor, isv_monto=isv, forma_pago=forma_pago, banco_id=banco_id,
                   referencia=referencia, mov_id=mov.id, usuario_nombre=usuario_nombre)
    db.add(pago)
    db.flush()
    registrar_asiento_para_movimiento(db, mov, isv_monto=isv)
    db.expire(cxc, ["pagos"])
    cxc.estado = CXC_PAGADA if q(cxc.saldo) <= 0 else CXC_PENDIENTE
    return pago


def _anular_mov(db: Session, mov: MovimientoFinanciero | None, nota: str, usuario_nombre: str):
    if not mov or mov.excluir_de_contabilidad:
        return
    mov.excluir_de_contabilidad = True
    mov.descripcion = f"{mov.descripcion or ''} ({nota})".strip()
    eliminar_asiento_de_movimiento(db, mov.id)
    if mov.turno_caja_id and mov.cuenta == "caja_chica":
        from app.routers.facturacion import _recalcular_turnos
        _recalcular_turnos(db, {mov.turno_caja_id: to_decimal(mov.monto)}, usuario_nombre, nota)


def anular_pago(db: Session, pago: CxCPago, motivo: str, usuario_nombre: str):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("Escribe el motivo para anular el pago.")
    if pago.anulado:
        raise ValueError("Ese pago ya estaba anulado.")
    pago.anulado = True
    pago.anulado_motivo = f"{motivo} — {usuario_nombre}, {datetime.utcnow():%d/%m/%Y}"
    cxc = pago.cxc
    _anular_mov(db, db.get(MovimientoFinanciero, pago.mov_id) if pago.mov_id else None,
                f"ANULADO: pago de {cxc.numero} — {motivo}", usuario_nombre)
    db.flush()
    db.expire(cxc, ["pagos"])
    if cxc.estado != CXC_ANULADA:
        cxc.estado = CXC_PAGADA if q(cxc.saldo) <= 0 else CXC_PENDIENTE


def anular_cuenta(db: Session, cxc: CuentaPorCobrar, motivo: str, usuario_nombre: str):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("Escribe el motivo para anular la cuenta.")
    if cxc.estado == CXC_ANULADA:
        raise ValueError("Esta cuenta ya estaba anulada.")
    if list(cxc.pagos):
        raise ValueError("Esta cuenta tiene pagos registrados: anula primero esos pagos.")
    cxc.estado = CXC_ANULADA
    cxc.anulada_motivo, cxc.anulada_por, cxc.anulada_en = motivo, usuario_nombre, datetime.utcnow()
    if cxc.mov_salida_id:
        _anular_mov(db, db.get(MovimientoFinanciero, cxc.mov_salida_id), f"ANULADO: préstamo {cxc.numero} — {motivo}", usuario_nombre)


def prestamos_por_cobrar_a(db: Session, instante: datetime) -> Decimal:
    """Lo que falta por cobrar de los préstamos dados antes de `instante` (para el Balance)."""
    total = CERO
    for c in db.query(CuentaPorCobrar).filter(CuentaPorCobrar.tipo == CXC_PRESTAMO, CuentaPorCobrar.estado != CXC_ANULADA,
                                              CuentaPorCobrar.fecha < instante).all():
        pagado = sum((to_decimal(p.monto) for p in c.pagos if p.fecha < instante), CERO)
        total += to_decimal(c.monto) - pagado
    return q(total)
