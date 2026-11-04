"""Cuentas por cobrar anotadas a mano (ventas al crédito y préstamos) y
sus pagos. Solo crea tablas nuevas.

IMPORTANTE: revision ID de 32 caracteres o menos.

Revision ID: 0038_cxc
Revises: 0037_bancos
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0038_cxc"
down_revision = "0037_bancos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cuentas_por_cobrar",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("numero", sa.String(20), nullable=False, unique=True),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=True),
        sa.Column("deudor", sa.String(150), nullable=False),
        sa.Column("telefono", sa.String(40), server_default=""),
        sa.Column("concepto", sa.Text(), server_default=""),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("con_isv", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("isv_monto", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("fecha", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("vence", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(12), nullable=False, server_default="pendiente"),
        sa.Column("cuenta_salida", sa.String(20), nullable=True),
        sa.Column("banco_id", sa.Integer(), sa.ForeignKey("bancos.id"), nullable=True),
        sa.Column("mov_salida_id", sa.Integer(), sa.ForeignKey("movimientos_financieros.id"), nullable=True),
        sa.Column("usuario_nombre", sa.String(150), server_default=""),
        sa.Column("anulada_motivo", sa.Text(), server_default=""),
        sa.Column("anulada_por", sa.String(150), server_default=""),
        sa.Column("anulada_en", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_cuentas_por_cobrar_numero", "cuentas_por_cobrar", ["numero"], unique=True)
    op.create_table(
        "cxc_pagos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cxc_id", sa.Integer(), sa.ForeignKey("cuentas_por_cobrar.id"), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("isv_monto", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("forma_pago", sa.String(20), nullable=False, server_default="Efectivo"),
        sa.Column("banco_id", sa.Integer(), sa.ForeignKey("bancos.id"), nullable=True),
        sa.Column("referencia", sa.String(60), server_default=""),
        sa.Column("mov_id", sa.Integer(), sa.ForeignKey("movimientos_financieros.id"), nullable=True),
        sa.Column("usuario_nombre", sa.String(150), server_default=""),
        sa.Column("anulado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("anulado_motivo", sa.Text(), server_default=""),
    )
    op.create_index("ix_cxc_pagos_cxc_id", "cxc_pagos", ["cxc_id"])


def downgrade() -> None:
    op.drop_index("ix_cxc_pagos_cxc_id", table_name="cxc_pagos")
    op.drop_table("cxc_pagos")
    op.drop_index("ix_cuentas_por_cobrar_numero", table_name="cuentas_por_cobrar")
    op.drop_table("cuentas_por_cobrar")
