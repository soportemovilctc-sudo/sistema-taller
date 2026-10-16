"""Ajustes de inventario (varios productos a la vez, desde pantalla o Excel)
y costo guardado al momento de cada movimiento.

Agrega:
  - ajustes_inventario / ajustes_inventario_detalle: cada ajuste (AJ-000001)
    con sus productos, existencia antes/después, diferencia y valor al costo.
  - movimientos_inventario: existencia_anterior, costo_unitario y ajuste_id,
    para valorar en lempiras cada movimiento (ajustes incluidos).
  - detalle_ventas.costo_unitario y orden_repuestos.costo_unitario: costo
    del producto en el momento de venderlo/usarlo, para el costo de ventas
    de los Estados Financieros.
Todas las columnas nuevas quedan vacías (NULL) en los registros que ya
existen: no se modifica ningún dato anterior.

IMPORTANTE: revision ID de 32 caracteres o menos (ver la nota en
0025_sr_condicion_accesorios.py).

Revision ID: 0028_ajustes_inventario
Revises: 0027_turnos_caja
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0028_ajustes_inventario"
down_revision = "0027_turnos_caja"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ajustes_inventario",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("numero", sa.String(20), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("usuario_nombre", sa.String(150), server_default=""),
        sa.Column("motivo", sa.String(60), nullable=False),
        sa.Column("observacion", sa.Text(), server_default=""),
        sa.Column("origen", sa.String(12), nullable=False, server_default="manual"),
        sa.Column("unidades_entrada", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unidades_salida", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valor_entrada", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("valor_salida", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("revierte_a_id", sa.Integer(), nullable=True),
        sa.Column("revertido_por_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_ajustes_inventario_numero", "ajustes_inventario", ["numero"], unique=True)
    op.create_index("ix_ajustes_inventario_fecha", "ajustes_inventario", ["fecha"])

    op.create_table(
        "ajustes_inventario_detalle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ajuste_id", sa.Integer(), sa.ForeignKey("ajustes_inventario.id"), nullable=False),
        sa.Column("producto_id", sa.Integer(), sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("producto_codigo", sa.String(50), server_default=""),
        sa.Column("producto_nombre", sa.String(150), server_default=""),
        sa.Column("existencia_anterior", sa.Integer(), nullable=False),
        sa.Column("existencia_nueva", sa.Integer(), nullable=False),
        sa.Column("diferencia", sa.Integer(), nullable=False),
        sa.Column("costo_unitario", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.create_index("ix_ajustes_inventario_detalle_ajuste_id", "ajustes_inventario_detalle", ["ajuste_id"])
    op.create_index("ix_ajustes_inventario_detalle_producto_id", "ajustes_inventario_detalle", ["producto_id"])

    with op.batch_alter_table("movimientos_inventario") as batch_op:
        batch_op.add_column(sa.Column("existencia_anterior", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("costo_unitario", sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column("ajuste_id", sa.Integer(), nullable=True))
    op.create_index("ix_movimientos_inventario_ajuste_id", "movimientos_inventario", ["ajuste_id"])

    with op.batch_alter_table("detalle_ventas") as batch_op:
        batch_op.add_column(sa.Column("costo_unitario", sa.Numeric(10, 2), nullable=True))
    with op.batch_alter_table("orden_repuestos") as batch_op:
        batch_op.add_column(sa.Column("costo_unitario", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orden_repuestos") as batch_op:
        batch_op.drop_column("costo_unitario")
    with op.batch_alter_table("detalle_ventas") as batch_op:
        batch_op.drop_column("costo_unitario")
    op.drop_index("ix_movimientos_inventario_ajuste_id", table_name="movimientos_inventario")
    with op.batch_alter_table("movimientos_inventario") as batch_op:
        batch_op.drop_column("ajuste_id")
        batch_op.drop_column("costo_unitario")
        batch_op.drop_column("existencia_anterior")
    op.drop_index("ix_ajustes_inventario_detalle_producto_id", table_name="ajustes_inventario_detalle")
    op.drop_index("ix_ajustes_inventario_detalle_ajuste_id", table_name="ajustes_inventario_detalle")
    op.drop_table("ajustes_inventario_detalle")
    op.drop_index("ix_ajustes_inventario_fecha", table_name="ajustes_inventario")
    op.drop_index("ix_ajustes_inventario_numero", table_name="ajustes_inventario")
    op.drop_table("ajustes_inventario")
