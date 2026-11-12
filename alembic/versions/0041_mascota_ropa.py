"""Ropero de la mascota: qué lleva puesto cada usuario (cabeza, ojos,
cuello, en la mano) y si se viste sola según la temporada. Solo agrega una
columna nueva (vacía = traje de temporada encendido y nada más).

Revision ID: 0041_mascota_ropa
Revises: 0040_comision_tarjeta
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0041_mascota_ropa"
down_revision = "0040_comision_tarjeta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios") as b:
        b.add_column(sa.Column("mascota_ropa", sa.String(120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("usuarios") as b:
        b.drop_column("mascota_ropa")
