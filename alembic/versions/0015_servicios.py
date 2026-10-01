"""agrega catalogo de servicios (precio de venta y costo opcional) y la
posibilidad de agregarlos a una orden de servicio (OrdenServicioExtra),
igual que ya existe para repuestos: nueva columna servicios_subtotal en
ordenes_servicio, tabla servicios y tabla orden_servicios_extra

Revision ID: 0015_servicios
Revises: 0014_notificaciones_whatsapp
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_servicios"
down_revision = "0014_notificaciones_whatsapp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ordenes_servicio",
        sa.Column("servicios_subtotal", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.create_table(
        "servicios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(150), nullable=False, unique=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("categoria", sa.String(80), nullable=True),
        sa.Column("precio_venta", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("costo", sa.Numeric(10, 2), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_servicios_nombre", "servicios", ["nombre"])
    op.create_table(
        "orden_servicios_extra",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("orden_id", sa.Integer(), sa.ForeignKey("ordenes_servicio.id"), nullable=False),
        sa.Column("servicio_id", sa.Integer(), sa.ForeignKey("servicios.id"), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("precio_unitario", sa.Numeric(10, 2), nullable=False),
        sa.Column("costo_unitario", sa.Numeric(10, 2), nullable=True),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=True),
        sa.Column("usuario_nombre", sa.String(150), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("orden_servicios_extra")
    op.drop_index("ix_servicios_nombre", table_name="servicios")
    op.drop_table("servicios")
    op.drop_column("ordenes_servicio", "servicios_subtotal")
