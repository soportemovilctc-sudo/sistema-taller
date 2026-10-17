"""Compras: precio de venta en el detalle de la solicitud y precio
anterior/nuevo en el detalle de la recepción. Solo columnas nuevas (vacías).

IMPORTANTE: revision ID de 32 caracteres o menos.

Revision ID: 0031_compras_precio
Revises: 0030_compras
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0031_compras_precio"
down_revision = "0030_compras"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("solicitudes_compra_detalle") as batch_op:
        batch_op.add_column(sa.Column("precio_venta", sa.Numeric(10, 2), nullable=True))
    with op.batch_alter_table("recepciones_compra_detalle") as batch_op:
        batch_op.add_column(sa.Column("precio_anterior", sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column("precio_nuevo", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recepciones_compra_detalle") as batch_op:
        batch_op.drop_column("precio_nuevo")
        batch_op.drop_column("precio_anterior")
    with op.batch_alter_table("solicitudes_compra_detalle") as batch_op:
        batch_op.drop_column("precio_venta")
