"""conecta ordenes de servicio con inventario: repuestos usados en la orden

Revision ID: 0007_repuestos_orden
Revises: 0006_dias_vencido_alerta
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_repuestos_orden"
down_revision = "0006_dias_vencido_alerta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ordenes_servicio",
        sa.Column("repuestos_subtotal", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    with op.batch_alter_table("ventas") as batch_op:
        batch_op.add_column(sa.Column("orden_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_ventas_orden_id", "ordenes_servicio", ["orden_id"], ["id"]
        )
    op.create_table(
        "orden_repuestos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("orden_id", sa.Integer(), sa.ForeignKey("ordenes_servicio.id"), nullable=False),
        sa.Column("producto_id", sa.Integer(), sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("venta_id", sa.Integer(), sa.ForeignKey("ventas.id"), nullable=True),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("precio_unitario", sa.Numeric(10, 2), nullable=False),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=True),
        sa.Column("usuario_nombre", sa.String(150), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("orden_repuestos")
    with op.batch_alter_table("ventas") as batch_op:
        batch_op.drop_constraint("fk_ventas_orden_id", type_="foreignkey")
        batch_op.drop_column("orden_id")
    op.drop_column("ordenes_servicio", "repuestos_subtotal")
