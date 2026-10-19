"""Acceso al equipo en la orden: tipo de bloqueo (PIN, patrón, contraseña,
huella, rostro...), contraseña, PIN de la SIM y cuenta Google/iCloud.
Solo agrega columnas nuevas (vacías); no toca datos existentes.

IMPORTANTE: revision ID de 32 caracteres o menos.

Revision ID: 0034_acceso_equipo
Revises: 0033_mejoras_zafra
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0034_acceso_equipo"
down_revision = "0033_mejoras_zafra"
branch_labels = None
depends_on = None

COLUMNAS = (
    ("tipo_bloqueo", 80), ("contrasena", 100), ("pin_sim", 20), ("cuenta_correo", 150), ("cuenta_contrasena", 100),
)


def upgrade() -> None:
    with op.batch_alter_table("ordenes_servicio") as b:
        for nombre, largo in COLUMNAS:
            b.add_column(sa.Column(nombre, sa.String(largo), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ordenes_servicio") as b:
        for nombre, _ in reversed(COLUMNAS):
            b.drop_column(nombre)
