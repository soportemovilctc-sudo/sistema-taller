"""Varios bancos: tabla bancos (con Banco Atlántida como principal) y
banco_id en movimientos y abonos. Los registros existentes quedan con
banco_id vacío = Banco Atlántida; no se cambia ningún dato.

IMPORTANTE: revision ID de 32 caracteres o menos.

Revision ID: 0037_bancos
Revises: 0036_notas
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0037_bancos"
down_revision = "0036_notas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bancos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("numero_cuenta", sa.String(60), server_default=""),
        sa.Column("tipo_cuenta", sa.String(40), server_default=""),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("principal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creado", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.execute("INSERT INTO bancos (nombre, numero_cuenta, tipo_cuenta, activo, principal) "
               "VALUES ('Banco Atlántida', '', '', true, true)")
    with op.batch_alter_table("movimientos_financieros") as b:
        b.add_column(sa.Column("banco_id", sa.Integer(), sa.ForeignKey("bancos.id", name="fk_mov_banco"), nullable=True))
        b.create_index("ix_movimientos_financieros_banco_id", ["banco_id"])
    with op.batch_alter_table("pagos") as b:
        b.add_column(sa.Column("banco_id", sa.Integer(), sa.ForeignKey("bancos.id", name="fk_pago_banco"), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("pagos") as b:
        b.drop_column("banco_id")
    with op.batch_alter_table("movimientos_financieros") as b:
        b.drop_index("ix_movimientos_financieros_banco_id")
        b.drop_column("banco_id")
    op.drop_table("bancos")
