"""agrega caja a productos

Revision ID: 0009_caja_producto
Revises: 0008_alerta_umbral_facturacion
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_caja_producto"
down_revision = "0008_alerta_umbral_facturacion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "productos",
        sa.Column("caja", sa.String(length=40), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("productos", "caja")
