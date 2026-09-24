"""agrega alerta_umbral_fiscal a configuracion_facturacion

Revision ID: 0008_alerta_umbral_facturacion
Revises: 0007_repuestos_orden
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_alerta_umbral_facturacion"
down_revision = "0007_repuestos_orden"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "configuracion_facturacion",
        sa.Column("alerta_umbral_fiscal", sa.Integer(), nullable=False, server_default="50"),
    )


def downgrade() -> None:
    op.drop_column("configuracion_facturacion", "alerta_umbral_fiscal")
