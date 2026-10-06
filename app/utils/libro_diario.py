"""Libro Diario: contabilidad de partida doble, generada automáticamente a
partir de cada MovimientoFinanciero relevante (ver app/models.py para
CuentaContable/AsientoContable/DetalleAsiento). Corre en PARALELO al libro
de caja de una sola entrada que ya existía — nunca lo modifica ni depende
de él para funcionar; si por cualquier motivo no se puede generar un
asiento, el movimiento de Caja/Orden/POS que lo originó se guarda igual
(ver el try/except al final de registrar_asiento_para_movimiento).

Cuentas usadas en esta primera versión (catálogo completo en la migración
0017_libro_diario):
  1101 Caja Chica (Fondo Fijo)      1104 Cuentas por Cobrar Empleados
  1102 Banco (Caja General)         1105 Crédito Fiscal ISV (aún sin usar)
  1103 Cuentas por Cobrar Clientes  2101 Débito Fiscal ISV por Pagar
  4101 Ventas                       4102 Otros Ingresos (Sobrante de Caja)
  5101 Gastos Operativos

Lo que todavía NO se contabiliza aquí (depende de funcionalidad que aún no
existe en el sistema, ver conversación con Ricardo):
  - Apertura de turno / Fondo de Sencillo (no existe un "abrir turno").
  - Sobrante y Faltante de caja (depende del arqueo a ciegas, no existe).
  - Crédito Fiscal ISV de gastos de caja chica con factura (los gastos de
    caja chica hoy no distinguen si tienen factura/ISV deducible).
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    CuentaContable, AsientoContable, DetalleAsiento, MovimientoFinanciero,
    CATEGORIA_DEPOSITO_BANCO, CATEGORIA_NOMINA_EFECTIVO,
)
from app.utils.numbering import siguiente_numero

CTA_CAJA_CHICA = "1101"
CTA_BANCO = "1102"
CTA_CXC_CLIENTES = "1103"
CTA_CXC_EMPLEADOS = "1104"
CTA_CREDITO_FISCAL_ISV = "1105"
CTA_DEBITO_FISCAL_ISV = "2101"
CTA_VENTAS = "4101"
CTA_OTROS_INGRESOS = "4102"
CTA_GASTOS_OPERATIVOS = "5101"

# Categorías de MovimientoFinanciero que se tratan como "Cobro a Cliente
# (Factura pendiente)": el ingreso (la venta) ya se había reconocido antes
# (al agregar el repuesto/servicio a la orden); esto es solo la entrada de
# efectivo que lo cancela.
CATEGORIAS_COBRO_CLIENTE = {"Cobro de caja", "Abono de orden", "Cancelación de orden (automático)"}

# Categorías que representan una venta nueva reconocida al contado.
CATEGORIAS_VENTA_CONTADO = {"Venta de repuesto (orden)", "Venta de servicio (orden)", "Venta POS"}

CATEGORIA_OTRO_INGRESO = "Otros ingresos"
CATEGORIA_REVERSION_CANCELACION = "Reversión por orden cancelada"
CATEGORIAS_SALIDA_CAJA_CHICA = {
    "Salida de caja", "Crédito por garantía", "Compra menor", "Otro gasto de caja",
    CATEGORIA_NOMINA_EFECTIVO,
}


def generar_numero_asiento(db: Session) -> str:
    ultimo = db.query(AsientoContable).order_by(AsientoContable.id.desc()).first()
    return siguiente_numero(ultimo.numero_asiento if ultimo else None, "AC")


def _cuenta(db: Session, codigo: str) -> CuentaContable:
    cuenta = db.query(CuentaContable).filter(CuentaContable.codigo == codigo).first()
    if not cuenta:
        raise ValueError(f"No existe la cuenta contable {codigo} (¿falta aplicar la migración 0017?).")
    return cuenta


def _cuenta_caja_app(cuenta_caja_app: str) -> str:
    """Traduce el campo MovimientoFinanciero.cuenta ('caja_chica' | 'banco')
    al código de la cuenta contable correspondiente."""
    return CTA_BANCO if cuenta_caja_app == "banco" else CTA_CAJA_CHICA


def registrar_asiento(
    db: Session, fecha: datetime, concepto: str, tipo_evento: str, lineas: list[tuple[str, Decimal, Decimal]],
    referencia: str = "", movimiento_financiero_id: int | None = None, usuario_nombre: str | None = None,
) -> AsientoContable:
    """lineas: lista de (codigo_cuenta, debe, haber). Debe quedar balanceado
    (suma Debe == suma Haber) o se rechaza con ValueError antes de guardar
    nada."""
    total_debe = sum((Decimal(d) for _, d, _ in lineas), Decimal("0.00"))
    total_haber = sum((Decimal(h) for _, _, h in lineas), Decimal("0.00"))
    if abs(total_debe - total_haber) > Decimal("0.01"):
        raise ValueError(f"Asiento contable descuadrado: Debe {total_debe} != Haber {total_haber} ({concepto}).")

    asiento = AsientoContable(
        numero_asiento=generar_numero_asiento(db), fecha=fecha, concepto=concepto,
        tipo_evento=tipo_evento, referencia=referencia or "",
        movimiento_financiero_id=movimiento_financiero_id, usuario_nombre=usuario_nombre,
    )
    db.add(asiento)
    db.flush()
    for codigo, debe, haber in lineas:
        cuenta = _cuenta(db, codigo)
        db.add(DetalleAsiento(
            asiento_id=asiento.id, cuenta_id=cuenta.id,
            debe=Decimal(debe).quantize(Decimal("0.01")), haber=Decimal(haber).quantize(Decimal("0.01")),
        ))
    return asiento


def eliminar_asiento_de_movimiento(db: Session, movimiento_id: int) -> None:
    """Borra el asiento (y sus detalles, por cascada) ligado a un
    MovimientoFinanciero, si existe. Se usa cuando ese movimiento se edita
    (para regenerarlo con los datos nuevos) o se elimina desde Caja."""
    asiento = db.query(AsientoContable).filter(AsientoContable.movimiento_financiero_id == movimiento_id).first()
    if asiento:
        db.delete(asiento)
        db.flush()


def registrar_asiento_para_movimiento(
    db: Session, mov: MovimientoFinanciero, monto_neto: Decimal | None = None, isv_monto: Decimal | None = None,
) -> AsientoContable | None:
    """Genera (o regenera) el asiento del Libro Diario correspondiente a un
    MovimientoFinanciero, según su categoría/referencia. `mov` debe ya tener
    id (hacer db.flush() después de agregarlo, antes de llamar esto).

    monto_neto/isv_monto solo aplican a una venta al contado (repuesto,
    servicio o POS) cuando el que llama ya conoce el desglose exacto (por
    ejemplo el Punto de Venta, que calcula el ISV directamente); si no se
    pasan, se asume que todo el monto es Ventas sin ISV.

    Nunca lanza una excepción hacia quien llama: si algo falla al
    contabilizar (por ejemplo falta una cuenta), el movimiento de Caja que
    lo originó igual se guarda — el Libro Diario es una capa adicional, no
    debe poder bloquear el día a día de Caja."""
    try:
        cuenta_caja = _cuenta_caja_app(mov.cuenta)
        fecha = mov.fecha or datetime.utcnow()

        if mov.referencia == "Egreso mayor":
            return registrar_asiento(
                db, fecha, f"Egreso mayor ({mov.categoria}) - {mov.descripcion or ''}".strip(" -"),
                "egreso_mayor", [(CTA_GASTOS_OPERATIVOS, mov.monto, 0), (CTA_BANCO, 0, mov.monto)],
                referencia=mov.referencia, movimiento_financiero_id=mov.id, usuario_nombre=mov.usuario_nombre,
            )

        if mov.categoria == CATEGORIA_OTRO_INGRESO:
            return registrar_asiento(
                db, fecha, f"Otro ingreso de caja - {mov.descripcion or ''}".strip(" -"),
                "otro_ingreso", [(CTA_CAJA_CHICA, mov.monto, 0), (CTA_OTROS_INGRESOS, 0, mov.monto)],
                referencia=mov.referencia, movimiento_financiero_id=mov.id, usuario_nombre=mov.usuario_nombre,
            )

        if mov.categoria == CATEGORIA_DEPOSITO_BANCO:
            # Depósito bancario: el efectivo no se gasta, se traslada de Caja
            # Chica a Banco. Esta fila (la salida de Caja Chica) es la que
            # genera el asiento completo y balanceado; la entrada en Banco
            # que la acompaña (ver caja_salida_crear) no genera uno propio,
            # para no duplicar el mismo traslado dos veces en el Libro Diario.
            return registrar_asiento(
                db, fecha, f"Depósito bancario - {mov.descripcion or ''}".strip(" -"),
                "deposito_banco", [(CTA_BANCO, mov.monto, 0), (CTA_CAJA_CHICA, 0, mov.monto)],
                referencia=mov.referencia, movimiento_financiero_id=mov.id, usuario_nombre=mov.usuario_nombre,
            )

        if mov.categoria in CATEGORIAS_SALIDA_CAJA_CHICA:
            return registrar_asiento(
                db, fecha, f"{mov.categoria} - {mov.descripcion or ''}".strip(" -"),
                "gasto_caja_chica", [(CTA_GASTOS_OPERATIVOS, mov.monto, 0), (CTA_CAJA_CHICA, 0, mov.monto)],
                referencia=mov.referencia, movimiento_financiero_id=mov.id, usuario_nombre=mov.usuario_nombre,
            )

        if mov.categoria in CATEGORIAS_COBRO_CLIENTE:
            return registrar_asiento(
                db, fecha, f"Cobro a cliente - {mov.descripcion or ''}".strip(" -"),
                "cobro_cliente", [(cuenta_caja, mov.monto, 0), (CTA_CXC_CLIENTES, 0, mov.monto)],
                referencia=mov.referencia, movimiento_financiero_id=mov.id, usuario_nombre=mov.usuario_nombre,
            )

        if mov.categoria in CATEGORIAS_VENTA_CONTADO:
            neto = monto_neto if monto_neto is not None else mov.monto
            isv = (isv_monto or Decimal("0.00"))
            lineas = [(cuenta_caja, mov.monto, 0), (CTA_VENTAS, 0, neto)]
            if isv > 0:
                lineas.append((CTA_DEBITO_FISCAL_ISV, 0, isv))
            return registrar_asiento(
                db, fecha, f"Venta al contado - {mov.descripcion or ''}".strip(" -"),
                "venta_contado", lineas,
                referencia=mov.referencia, movimiento_financiero_id=mov.id, usuario_nombre=mov.usuario_nombre,
            )

        if mov.categoria == CATEGORIA_REVERSION_CANCELACION:
            # Reversa el asiento de venta original: Debe Ventas, Haber Caja.
            # (Simplificación: no vuelve a descomponer el ISV de la venta
            # original; ver nota al inicio del archivo.)
            return registrar_asiento(
                db, fecha, f"Reversión por orden cancelada - {mov.descripcion or ''}".strip(" -"),
                "reversion_cancelacion", [(CTA_VENTAS, mov.monto, 0), (cuenta_caja, 0, mov.monto)],
                referencia=mov.referencia, movimiento_financiero_id=mov.id, usuario_nombre=mov.usuario_nombre,
            )

        return None  # categoría todavía sin mapeo contable — no bloquea el movimiento.
    except Exception:
        return None
