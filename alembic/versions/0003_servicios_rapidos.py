"""plantillas de servicio rapido (autollenado de orden + cobros)

Revision ID: 0003_servicios_rapidos
Revises: 0002_facturacion_catalogo
Create Date: 2026-09-17

"""
from alembic import op
import sqlalchemy as sa

revision = "0003_servicios_rapidos"
down_revision = "0002_facturacion_catalogo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "servicios_rapidos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("falla_reportada", sa.Text, server_default=""),
        sa.Column("estado_fisico", sa.Text, server_default=""),
        sa.Column("observaciones", sa.Text, server_default=""),
        sa.Column("trabajo_realizado", sa.Text, server_default=""),
        sa.Column("dias_plazo", sa.Integer, server_default="0"),
        sa.Column("cotizacion", sa.Numeric(10, 2), server_default="0"),
        sa.Column("recargo_pct", sa.Numeric(6, 2), server_default="0"),
        sa.Column("orden", sa.Integer, server_default="0"),
        sa.Column("creado_en", sa.DateTime, nullable=True),
        sa.UniqueConstraint("nombre", name="uq_servicios_rapidos_nombre"),
    )


def downgrade() -> None:
    op.drop_table("servicios_rapidos")
