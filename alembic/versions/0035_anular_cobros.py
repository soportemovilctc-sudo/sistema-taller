"""Anular el cobro junto con la factura: abonos (pagos) y ventas del Punto de
Venta pueden quedar anulados (dejan de sumar en Caja, Inicio y reportes).
Solo agrega columnas nuevas; no toca datos existentes.

IMPORTANTE: revision ID de 32 caracteres o menos.

Revision ID: 0035_anular_cobros
Revises: 0034_acceso_equipo
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0035_anular_cobros"
down_revision = "0034_acceso_equipo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pagos") as b:
        b.add_column(sa.Column("anulado", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("anulado_factura_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("ventas") as b:
        b.add_column(sa.Column("anulada", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("ventas") as b:
        b.drop_column("anulada")
    with op.batch_alter_table("pagos") as b:
        b.drop_column("anulado_factura_id")
        b.drop_column("anulado")
