"""La contabilidad (Ingresos/Caja/Utilidad Neta/Contabilidad) deja de sumar
las ordenes en si (se contaban dos veces: al agregar el repuesto/servicio,
y otra vez al cobrarlo) y pasa a sumar solo las Facturas que se emitan.

- Agrega "excluir_de_contabilidad" a movimientos_financieros: las filas ya
  existentes de las categorias viejas (Venta de repuesto/servicio (orden),
  Abono de orden, Cancelacion de orden (automatico), Reversion por orden
  cancelada, Correccion de repuesto/servicio (orden)) se marcan con este
  campo en vez de borrarse, para que dejen de sumar pero el historial real
  nunca se pierda.
- Agrega "factura_id" a movimientos_financieros, para enlazar el ingreso
  nuevo con la Factura que lo genero (ver CATEGORIA_VENTA_FACTURADA).
- Por cada Factura YA EMITIDA (no anulada) de una orden, que todavia no
  tiene su ingreso contable (porque antes una Factura era solo un
  documento, nunca generaba un movimiento), se crea ahora ese ingreso con
  la fecha de la factura, para que el historial de meses anteriores no
  quede en cero.

Revision ID: 0020_facturas_contabilidad
Revises: 0019_nomina_renombrar_deposito
Create Date: 2026-10-06
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "0020_facturas_contabilidad"
down_revision = "0019_nomina_renombrar_deposito"
branch_labels = None
depends_on = None


def _como_datetime(valor):
    """SQLite devuelve la fecha como texto crudo en una consulta SQL
    directa (en vez de un datetime de Python, como sí hace PostgreSQL vía
    psycopg2); esto la normaliza en ambos casos."""
    if valor is None or isinstance(valor, datetime):
        return valor
    texto = str(valor)
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texto, fmt)
        except ValueError:
            continue
    return valor


CATEGORIAS_ORDEN_EXCLUIDAS_CONTABILIDAD = [
    "Venta de repuesto (orden)", "Venta de servicio (orden)",
    "Abono de orden", "Cancelación de orden (automático)",
    "Reversión por orden cancelada",
    "Corrección de repuesto (orden)", "Corrección de servicio (orden)",
]
CATEGORIA_VENTA_FACTURADA = "Venta facturada (orden)"


def upgrade() -> None:
    with op.batch_alter_table("movimientos_financieros") as batch_op:
        batch_op.add_column(sa.Column(
            "excluir_de_contabilidad", sa.Boolean(), nullable=False, server_default=sa.false()
        ))
        batch_op.add_column(sa.Column("factura_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_movimientos_financieros_factura_id",
            "movimientos_financieros", ["factura_id"], ["id"]
        )

    conn = op.get_bind()

    # 1) Las filas viejas de ordenes: se quedan en la base de datos tal
    #    cual, solo se marcan para que dejen de sumar en la contabilidad.
    conn.execute(sa.text(
        "UPDATE movimientos_financieros SET excluir_de_contabilidad = true "
        "WHERE categoria IN :categorias"
    ).bindparams(sa.bindparam("categorias", expanding=True)), {
        "categorias": CATEGORIAS_ORDEN_EXCLUIDAS_CONTABILIDAD,
    })

    # 2) Por cada factura ya emitida (no anulada) de una orden, se crea el
    #    ingreso contable que nunca existio (antes la Factura era solo un
    #    documento). Las facturas de POS (venta_id, sin orden_id) no se
    #    tocan: esas ya generan su ingreso al momento de la venta.
    facturas = conn.execute(sa.text(
        "SELECT f.id AS factura_id, f.numero_documento, f.total, f.fecha_emision, "
        "       f.usuario_nombre, o.numero_orden "
        "FROM facturas f "
        "JOIN ordenes_servicio o ON o.id = f.orden_id "
        "WHERE f.orden_id IS NOT NULL AND f.anulada = false"
    )).mappings().all()

    if facturas:
        movimientos_tabla = sa.table(
            "movimientos_financieros",
            sa.column("tipo", sa.String),
            sa.column("categoria", sa.String),
            sa.column("monto", sa.Numeric),
            sa.column("fecha", sa.DateTime),
            sa.column("descripcion", sa.Text),
            sa.column("usuario_nombre", sa.String),
            sa.column("referencia", sa.String),
            sa.column("cuenta", sa.String),
            sa.column("excluir_de_contabilidad", sa.Boolean),
            sa.column("factura_id", sa.Integer),
        )
        op.bulk_insert(movimientos_tabla, [
            {
                "tipo": "ingreso",
                "categoria": CATEGORIA_VENTA_FACTURADA,
                "monto": f["total"],
                "fecha": _como_datetime(f["fecha_emision"]),
                "descripcion": f"Factura {f['numero_documento']} - Orden {f['numero_orden']}",
                "usuario_nombre": f["usuario_nombre"],
                "referencia": f["numero_orden"],
                "cuenta": "caja_chica",
                "excluir_de_contabilidad": False,
                "factura_id": f["factura_id"],
            }
            for f in facturas
        ])


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM movimientos_financieros WHERE categoria = :categoria AND factura_id IS NOT NULL"
    ), {"categoria": CATEGORIA_VENTA_FACTURADA})
    conn.execute(sa.text(
        "UPDATE movimientos_financieros SET excluir_de_contabilidad = false "
        "WHERE categoria IN :categorias"
    ).bindparams(sa.bindparam("categorias", expanding=True)), {
        "categorias": CATEGORIAS_ORDEN_EXCLUIDAS_CONTABILIDAD,
    })
    with op.batch_alter_table("movimientos_financieros") as batch_op:
        batch_op.drop_constraint("fk_movimientos_financieros_factura_id", type_="foreignkey")
        batch_op.drop_column("factura_id")
        batch_op.drop_column("excluir_de_contabilidad")
