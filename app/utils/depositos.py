"""Depósitos de Caja Chica al banco que quedaron registrados como una
entrada normal al banco (un «Cobro de caja» por transferencia, un ingreso a
mano...). Así el dinero aparecía dos veces: seguía en la caja y además en el
banco, y contaba como venta.

convertir_en_deposito() lo deja como un Depósito bancario de verdad: la
entrada al banco pasa a ser la mitad «Banco» del depósito y se crea su
salida de Caja Chica (mismo monto, misma fecha y misma caja), vinculadas
entre sí. Si esa caja ya estaba cerrada, se recalcula su arqueo y queda en
su bitácora. Nada se borra."""
import unicodedata

from sqlalchemy.orm import Session

from app.models import (
    MovimientoFinanciero, TurnoCaja, TurnoCajaEvento, CATEGORIA_DEPOSITO_BANCO, CATEGORIA_VENTA_FACTURADA,
    TURNO_ABIERTO,
)
from app.utils.calculations import to_decimal
from app.utils.caja_calculos import CUENTA_BANCO, CUENTA_CAJA_CHICA
from app.utils.libro_diario import eliminar_asiento_de_movimiento, registrar_asiento_para_movimiento

CATEGORIAS_NO_CONVERTIBLES = (CATEGORIA_DEPOSITO_BANCO, CATEGORIA_VENTA_FACTURADA, "Venta POS")
REFERENCIA_CORREGIDO = "Depósito bancario (corregido)"


def _sin_acentos(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


def es_convertible(m: MovimientoFinanciero) -> bool:
    """Entrada al banco registrada a mano (no una venta del POS ni una factura)."""
    return (m.tipo == "ingreso" and m.cuenta == CUENTA_BANCO and not m.excluir_de_contabilidad
            and m.categoria not in CATEGORIAS_NO_CONVERTIBLES and not m.factura_id
            and not m.movimiento_vinculado_id)


def parece_deposito(m: MovimientoFinanciero) -> bool:
    texto = " ".join(_sin_acentos(x) for x in (m.descripcion, m.cliente_nombre, m.num_referencia, m.referencia, m.categoria))
    return "deposit" in texto


def sospechosos(db: Session) -> list[MovimientoFinanciero]:
    filas = db.query(MovimientoFinanciero).filter(
        MovimientoFinanciero.tipo == "ingreso", MovimientoFinanciero.cuenta == CUENTA_BANCO,
        MovimientoFinanciero.categoria != CATEGORIA_DEPOSITO_BANCO,
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ).order_by(MovimientoFinanciero.fecha.asc()).all()
    return [m for m in filas if es_convertible(m) and parece_deposito(m)]


def convertir_en_deposito(db: Session, mov: MovimientoFinanciero, usuario_nombre: str):
    """Devuelve (salida de caja creada, mensaje de error)."""
    if not mov or not es_convertible(mov):
        return None, "Esa entrada no se puede convertir: solo entradas al banco registradas a mano (no ventas del POS ni facturas)."
    monto = to_decimal(mov.monto).quantize(to_decimal("0.01"))
    categoria_antes = mov.categoria
    eliminar_asiento_de_movimiento(db, mov.id)
    nota = f"(corregido: antes «{categoria_antes}»" + (f" · {mov.metodo_pago}" if mov.metodo_pago else "") + f", por {usuario_nombre})"
    mov.categoria = CATEGORIA_DEPOSITO_BANCO
    mov.descripcion = f"{(mov.descripcion or '').strip()} {nota}".strip()
    if mov.estado_conciliacion == "pendiente":
        mov.estado_conciliacion = None

    salida = MovimientoFinanciero(
        tipo="gasto", categoria=CATEGORIA_DEPOSITO_BANCO, monto=monto,
        descripcion=f"Depósito al banco · {(mov.cliente_nombre or '').strip() or 'corregido desde una entrada al banco'}",
        usuario_nombre=mov.usuario_nombre, referencia=REFERENCIA_CORREGIDO, cuenta=CUENTA_CAJA_CHICA,
        fecha=mov.fecha, turno_caja_id=mov.turno_caja_id, movimiento_vinculado_id=mov.id,
    )
    db.add(salida)
    db.flush()
    if mov.turno_caja_id is None and salida.turno_caja_id is not None:
        salida.turno_caja_id = None  # no la mete en la caja abierta de hoy
    mov.movimiento_vinculado_id = salida.id
    db.flush()
    registrar_asiento_para_movimiento(db, salida)

    if mov.turno_caja_id:
        turno = db.get(TurnoCaja, mov.turno_caja_id)
        if turno and turno.estado != TURNO_ABIERTO:
            from app.routers.turnos_caja import _recalcular_arqueo
            from datetime import datetime
            antes_e, antes_d = to_decimal(turno.efectivo_esperado or 0), to_decimal(turno.diferencia or 0)
            _recalcular_arqueo(db, turno)
            db.add(TurnoCajaEvento(
                turno_id=turno.id, accion="edicion", usuario_nombre=usuario_nombre, fecha=datetime.utcnow(),
                detalle=(f"Entrada al banco #{mov.id} de L {monto:,.2f} corregida como Depósito bancario: ahora sale de esta caja. "
                         f"Esperado: L {antes_e:,.2f} → L {to_decimal(turno.efectivo_esperado):,.2f}; "
                         f"diferencia: L {antes_d:,.2f} → L {to_decimal(turno.diferencia or 0):,.2f}"),
            ))
    return salida, None
