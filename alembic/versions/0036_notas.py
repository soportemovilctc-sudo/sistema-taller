"""Notas personales de cada usuario (libreta privada con formato,
recordatorio, importante y hecha). Solo crea una tabla nueva.

IMPORTANTE: revision ID de 32 caracteres o menos.

Revision ID: 0036_notas
Revises: 0035_anular_cobros
Create Date: 2026-11-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0036_notas"
down_revision = "0035_anular_cobros"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("titulo", sa.String(150), server_default=""),
        sa.Column("contenido", sa.Text(), server_default=""),
        sa.Column("contenido_texto", sa.Text(), server_default=""),
        sa.Column("color", sa.String(20), server_default=""),
        sa.Column("importante", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hecha", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hecha_en", sa.DateTime(), nullable=True),
        sa.Column("fecha_recordatorio", sa.Date(), nullable=True),
        sa.Column("creada", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("actualizada", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notas_usuario_id", "notas", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_notas_usuario_id", table_name="notas")
    op.drop_table("notas")
