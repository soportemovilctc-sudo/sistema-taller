"""agrega dias_vencido_alerta a configuracion

Revision ID: 0006_dias_vencido_alerta
Revises: 0005_logo_dias_seguridad
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_dias_vencido_alerta"
down_revision = "0005_logo_dias_seguridad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "configuracion",
        sa.Column("dias_vencido_alerta", sa.Integer(), nullable=False, server_default="3"),
    )


def downgrade() -> None:
    op.drop_column("configuracion", "dias_vencido_alerta")
