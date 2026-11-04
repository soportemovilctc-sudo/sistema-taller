"""Textos: «gasto» pasa a llamarse «egreso». Renombra la categoría guardada
«Otro gasto de caja» → «Otro egreso de caja» y la cuenta contable 5101
«Gastos Operativos» → «Egresos Operativos». Solo cambia nombres, no montos.

IMPORTANTE: revision ID de 32 caracteres o menos.

Revision ID: 0039_egresos
Revises: 0038_cxc
Create Date: 2026-11-04
"""
from alembic import op

revision = "0039_egresos"
down_revision = "0038_cxc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE movimientos_financieros SET categoria = 'Otro egreso de caja' WHERE categoria = 'Otro gasto de caja'")
    op.execute("UPDATE cuentas_contables SET nombre = 'Egresos Operativos' WHERE codigo = '5101' AND nombre = 'Gastos Operativos'")


def downgrade() -> None:
    op.execute("UPDATE movimientos_financieros SET categoria = 'Otro gasto de caja' WHERE categoria = 'Otro egreso de caja'")
    op.execute("UPDATE cuentas_contables SET nombre = 'Gastos Operativos' WHERE codigo = '5101' AND nombre = 'Egresos Operativos'")
