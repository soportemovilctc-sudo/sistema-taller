"""Renombra la categoria "Deposito bancario (remesa)" a "Deposito bancario"
en las filas ya existentes de movimientos_financieros (Ricardo pidio quitar
el parentesis "(remesa)" de la lista de Salida de caja); no borra ni
modifica ningun otro dato de esas filas, solo el texto de la categoria,
para que sigan coincidiendo con CATEGORIA_DEPOSITO_BANCO del codigo.

Revision ID: 0019_nomina_renombrar_deposito
Revises: 0018_remesa_banco
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_nomina_renombrar_deposito"
down_revision = "0018_remesa_banco"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "UPDATE movimientos_financieros SET categoria = 'Depósito bancario' "
        "WHERE categoria = 'Depósito bancario (remesa)'"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "UPDATE movimientos_financieros SET categoria = 'Depósito bancario (remesa)' "
        "WHERE categoria = 'Depósito bancario'"
    ))
