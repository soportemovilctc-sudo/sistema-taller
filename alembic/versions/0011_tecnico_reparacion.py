"""agrega tecnico_reparacion_id a ordenes_servicio: el tecnico que
realmente hizo la reparacion, que no siempre es el mismo que recibio el
equipo (tecnico_id)

Revision ID: 0011_tecnico_reparacion
Revises: 0010_categorias
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_tecnico_reparacion"
down_revision = "0010_categorias"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ordenes_servicio") as batch_op:
        batch_op.add_column(sa.Column("tecnico_reparacion_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_ordenes_servicio_tecnico_reparacion_id", "tecnicos", ["tecnico_reparacion_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("ordenes_servicio") as batch_op:
        batch_op.drop_constraint("fk_ordenes_servicio_tecnico_reparacion_id", type_="foreignkey")
        batch_op.drop_column("tecnico_reparacion_id")
