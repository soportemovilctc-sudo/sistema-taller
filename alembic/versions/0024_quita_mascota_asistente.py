"""Quita la mascota "Asistente" (Ricardo pidió eliminarla del sistema por
completo). Ya no aparece como opción en Apariencia (ver
MASCOTAS_DISPONIBLES en app/models.py) ni existe el código/las imágenes
que la dibujaban.

Si algún usuario ya la tenía elegida, su cuenta quedaría con
usuarios.mascota = 'asistente' -- un valor que ya no reconoce la
plantilla. Esta migración lo corrige en los datos ya existentes,
devolviendo a esos usuarios a "panda" (la mascota por default), para que
no se quede nadie con un valor huérfano.

Revision ID: 0024_quita_mascota_asistente
Revises: 0023_reclasifica_cuenta_bancaria
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_quita_mascota_asistente"
down_revision = "0023_reclasifica_cuenta_bancaria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    resultado = conn.execute(sa.text(
        "UPDATE usuarios SET mascota = 'panda' WHERE mascota = 'asistente'"
    ))
    print(f"[0024_quita_mascota_asistente] usuarios regresados a 'panda': {resultado.rowcount}")


def downgrade() -> None:
    # No tiene un "antes" al que volver: no se guarda registro de quién
    # tenía 'asistente' elegido antes de esta corrección.
    pass
