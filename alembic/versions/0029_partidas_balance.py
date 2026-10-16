"""Datos del Balance General registrados por el administrador (activos fijos,
otros activos, cuentas por pagar, préstamos, capital y retiros del dueño).
Solo agrega una tabla nueva; no toca ningún dato existente.

IMPORTANTE: revision ID de 32 caracteres o menos (ver la nota en
0025_sr_condicion_accesorios.py).

Revision ID: 0029_partidas_balance
Revises: 0028_ajustes_inventario
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0029_partidas_balance"
down_revision = "0028_ajustes_inventario"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partidas_balance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("descripcion", sa.String(200), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("fecha_baja", sa.Date(), nullable=True),
        sa.Column("vida_util_meses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notas", sa.Text(), server_default=""),
        sa.Column("usuario_nombre", sa.String(150), server_default=""),
        sa.Column("creado_en", sa.DateTime(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_partidas_balance_tipo", "partidas_balance", ["tipo"])


def downgrade() -> None:
    op.drop_index("ix_partidas_balance_tipo", table_name="partidas_balance")
    op.drop_table("partidas_balance")
