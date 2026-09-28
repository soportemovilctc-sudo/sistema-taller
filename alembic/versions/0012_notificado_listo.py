"""agrega notificado_listo y fecha_notificado_listo a ordenes_servicio:
para saber si ya se le avisó al cliente que su equipo está listo para
entregar

Revision ID: 0012_notificado_listo
Revises: 0011_tecnico_reparacion
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_notificado_listo"
down_revision = "0011_tecnico_reparacion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ordenes_servicio") as batch_op:
        batch_op.add_column(
            sa.Column("notificado_listo", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("fecha_notificado_listo", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ordenes_servicio") as batch_op:
        batch_op.drop_column("fecha_notificado_listo")
        batch_op.drop_column("notificado_listo")
