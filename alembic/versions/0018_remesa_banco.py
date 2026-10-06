"""agrega movimiento_vinculado_id a movimientos_financieros: vincula las dos
filas de un Deposito bancario (remesa) -- la salida de Caja Chica y su
contraparte, la entrada a Banco -- para que editar o eliminar una arrastre
a la otra y nunca queden descuadradas o huerfanas.

Revision ID: 0018_remesa_banco
Revises: 0017_libro_diario
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_remesa_banco"
down_revision = "0017_libro_diario"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("movimientos_financieros") as batch_op:
        batch_op.add_column(sa.Column("movimiento_vinculado_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_movimientos_financieros_movimiento_vinculado_id",
            "movimientos_financieros", ["movimiento_vinculado_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("movimientos_financieros") as batch_op:
        batch_op.drop_constraint("fk_movimientos_financieros_movimiento_vinculado_id", type_="foreignkey")
        batch_op.drop_column("movimiento_vinculado_id")
