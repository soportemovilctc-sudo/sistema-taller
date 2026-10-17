"""Historial de cambios de datos de los productos (costo, precio, nombre,
categoría...). Solo agrega una tabla nueva; no toca datos existentes.

IMPORTANTE: revision ID de 32 caracteres o menos.

Revision ID: 0032_historial_producto
Revises: 0031_compras_precio
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0032_historial_producto"
down_revision = "0031_compras_precio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "historial_productos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("producto_id", sa.Integer(), sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("usuario_nombre", sa.String(150), server_default=""),
        sa.Column("campo", sa.String(40), nullable=False),
        sa.Column("antes", sa.String(200), server_default=""),
        sa.Column("despues", sa.String(200), server_default=""),
        sa.Column("origen", sa.String(30), server_default=""),
    )
    op.create_index("ix_historial_productos_producto_id", "historial_productos", ["producto_id"])
    op.create_index("ix_historial_productos_fecha", "historial_productos", ["fecha"])


def downgrade() -> None:
    op.drop_index("ix_historial_productos_fecha", table_name="historial_productos")
    op.drop_index("ix_historial_productos_producto_id", table_name="historial_productos")
    op.drop_table("historial_productos")
