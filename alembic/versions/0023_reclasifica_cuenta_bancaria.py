"""Corrige la cuenta (Caja Chica vs Banco) de movimientos financieros que
quedaron mal clasificados: Ricardo reportó que los egresos pagados por
Transferencia o Tarjeta, y los ingresos cobrados por Transferencia o POS,
se estaban reflejando como si hubieran pasado por Caja Chica (efectivo),
cuando en realidad ese dinero nunca pasó físicamente por la caja.

Regla (la misma que ya aplicaba /caja/registrar desde el principio, ver
caja.py): SOLO Efectivo cuenta como Caja Chica. Cualquier otra forma de
pago (Transferencia, Tarjeta, Otro) cuenta como Banco.

Esta migración corrige datos YA EXISTENTES en dos partes, sin borrar ni
recalcular ningún monto:

  Parte A (egresos): un egreso que YA tenía una forma de pago no-efectivo
  elegida (por ejemplo desde la lista rápida de Reportes > Egresos) pero
  seguía marcado como Caja Chica -> se reclasifica a Banco. Es un simple
  cambio de columna, no hay nada que repartir.

  Parte B (ingresos de Facturas de orden y de Ventas POS): antes de este
  cambio estos ingresos nunca registraban su forma de pago, así que todos
  quedaban en Caja Chica por default, sin importar si el cliente pagó en
  efectivo, transferencia o tarjeta. Para cada uno se revisa cómo se cobró
  realmente (los abonos de la orden, o la forma de pago de la venta POS):
    - Si se cobró con un solo método: se reclasifica la cuenta según ese
      método (Efectivo se deja igual, cualquier otro pasa a Banco) y se
      completa el dato de forma de pago.
    - Si se cobró con más de un método (pago mixto) o no se pudo
      determinar, se deja exactamente igual que estaba y se avisa en el
      log para que se revise a mano -- no se parte el monto de una fila
      histórica para no arriesgar un dato que ya se usó en reportes
      anteriores.

No se toca el Libro Diario (asientos contables): es una capa adicional,
informativa, que no bloquea Caja/Reportes/Contabilidad (ver
app/utils/libro_diario.py). Puede quedar con alguna fila vieja mostrando
Caja Chica donde ahora el movimiento dice Banco; si eso llega a importar,
se puede corregir después a mano desde el Libro Diario.

Revision ID: 0023_reclasifica_cuenta_bancaria
Revises: 0022_efectos_apariencia
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_reclasifica_cuenta_bancaria"
down_revision = "0022_efectos_apariencia"
branch_labels = None
depends_on = None

FORMAS_NO_EFECTIVO = ("Transferencia", "Tarjeta", "Tarjeta (POS)", "Otro")


def upgrade() -> None:
    conn = op.get_bind()

    # --- Parte A: egresos con forma de pago no-efectivo ya elegida -------
    try:
        with conn.begin_nested():
            resultado = conn.execute(sa.text(
                "UPDATE movimientos_financieros SET cuenta = 'banco' "
                "WHERE tipo = 'gasto' AND cuenta = 'caja_chica' "
                "AND metodo_pago IN ('Transferencia', 'Tarjeta', 'Tarjeta (POS)', 'Otro')"
            ))
        print(f"[0023_reclasifica_cuenta_bancaria] egresos reclasificados a Banco: {resultado.rowcount}")
    except Exception as exc:
        print(
            "[0023_reclasifica_cuenta_bancaria] AVISO: no se pudieron reclasificar "
            f"los egresos ({exc!r})."
        )

    # --- Parte B: ingresos de Facturas de orden y Ventas POS --------------
    try:
        with conn.begin_nested():
            candidatos = conn.execute(sa.text(
                "SELECT id, categoria, referencia, factura_id "
                "FROM movimientos_financieros "
                "WHERE tipo = 'ingreso' AND cuenta = 'caja_chica' AND metodo_pago IS NULL "
                "  AND categoria IN ('Venta facturada (orden)', 'Venta POS')"
            )).mappings().all()
    except Exception as exc:
        print(
            "[0023_reclasifica_cuenta_bancaria] AVISO: no se pudo leer la lista de "
            f"ingresos a revisar ({exc!r})."
        )
        candidatos = []

    reclasificados = 0
    confirmados_efectivo = 0
    omitidos_mixtos = 0
    omitidos_sin_datos = 0

    for fila in candidatos:
        try:
            with conn.begin_nested():
                forma_unica = None

                if fila["categoria"] == "Venta facturada (orden)" and fila["factura_id"] is not None:
                    pagos = conn.execute(sa.text(
                        "SELECT p.forma_pago AS forma_pago "
                        "FROM pagos p "
                        "JOIN facturas f ON f.orden_id = p.orden_id "
                        "WHERE f.id = :factura_id AND p.fecha <= f.fecha_emision"
                    ), {"factura_id": fila["factura_id"]}).mappings().all()
                    formas = {p["forma_pago"] for p in pagos if p["forma_pago"]}
                    if len(formas) == 1:
                        forma_unica = next(iter(formas))
                    elif len(formas) == 0:
                        # Todavía sin abonos registrados a esa fecha: se
                        # confirma como Efectivo, igual que el
                        # comportamiento de siempre (no cambia la cuenta).
                        forma_unica = "Efectivo"
                    else:
                        omitidos_mixtos += 1
                        continue

                elif fila["categoria"] == "Venta POS" and fila["referencia"]:
                    venta = conn.execute(sa.text(
                        "SELECT forma_pago FROM ventas WHERE numero_venta = :numero_venta"
                    ), {"numero_venta": fila["referencia"]}).mappings().first()
                    forma_unica = venta["forma_pago"] if venta else None

                if not forma_unica:
                    omitidos_sin_datos += 1
                    continue

                if forma_unica == "Efectivo":
                    conn.execute(sa.text(
                        "UPDATE movimientos_financieros SET metodo_pago = :forma WHERE id = :id"
                    ), {"forma": forma_unica, "id": fila["id"]})
                    confirmados_efectivo += 1
                else:
                    conn.execute(sa.text(
                        "UPDATE movimientos_financieros SET metodo_pago = :forma, cuenta = 'banco' WHERE id = :id"
                    ), {"forma": forma_unica, "id": fila["id"]})
                    reclasificados += 1
        except Exception as exc:
            omitidos_sin_datos += 1
            print(
                "[0023_reclasifica_cuenta_bancaria] AVISO: se omitio el movimiento "
                f"id={fila.get('id')} ({exc!r})."
            )

    print(
        f"[0023_reclasifica_cuenta_bancaria] ingresos reclasificados a Banco: {reclasificados}, "
        f"confirmados como Efectivo (sin cambio): {confirmados_efectivo}, "
        f"omitidos por pago mixto: {omitidos_mixtos}, omitidos por falta de datos: {omitidos_sin_datos}."
    )


def downgrade() -> None:
    # Esta migración corrige datos (reclasifica una columna según hechos ya
    # ocurridos), no cambia el esquema -- no tiene un "antes" exacto al que
    # volver sin arriesgar deshacer también reclasificaciones correctas que
    # el propio código haya hecho después de aplicarla. Se deja sin acción,
    # igual que otras correcciones de datos de este mismo historial de
    # migraciones (ver 0019).
    pass
