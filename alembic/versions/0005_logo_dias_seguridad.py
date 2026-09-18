"""agrega logo en BD, dias en taller y opcion de imprimir PIN/patron

Revision ID: 0005_logo_dias_seguridad
Revises: 0004_condiciones_servicio
Create Date: 2026-09-18

"""
from alembic import op
import sqlalchemy as sa

revision = "0005_logo_dias_seguridad"
down_revision = "0004_condiciones_servicio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("configuracion", sa.Column("logo_data", sa.LargeBinary(), nullable=True))
    op.add_column("configuracion", sa.Column("logo_mime", sa.String(50), nullable=True))

    op.add_column("ordenes_servicio", sa.Column("fecha_cierre", sa.DateTime(), nullable=True))
    op.add_column(
        "ordenes_servicio",
        sa.Column("mostrar_seguridad_en_pdf", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("ordenes_servicio", "mostrar_seguridad_en_pdf")
    op.drop_column("ordenes_servicio", "fecha_cierre")
    op.drop_column("configuracion", "logo_mime")
    op.drop_column("configuracion", "logo_data")
