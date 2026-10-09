"""Agrega Condición física y Accesorios (opcionales) a las plantillas de
Servicio rápido (ver app/models.py: ServicioRapido).

Ricardo pidió que crear una orden fuera más rápido, en particular llenar
los "datos del equipo y su condición". Hoy "Servicio rápido" ya llena de
un clic Falla reportada, Diagnóstico, Trabajo realizado, Observaciones,
Cotización, Recargo y Fecha de entrega -- pero no toca los chips de
Condición física ni Accesorios entregados, así que esos siempre había que
marcarlos a mano. Con estas dos columnas, una plantilla como "Cambio de
pantalla" puede guardar también "Pantalla dañada" como condición típica,
y al aplicarla en una orden nueva se marca sola.

Son opcionales: una plantilla que las deje vacías (como todas las que ya
existían antes de esta migración) no toca la Condición/Accesorios ya
marcados en el formulario al aplicarse -- solo se sobrescriben cuando la
plantilla sí trae algo guardado (ver app/static/js/orden.js: aplicarChips
/ aplicarServicio).

NOTA: este archivo se llamó originalmente
"0025_servicio_rapido_condicion_accesorios" (revision ID de 41
caracteres). Eso tumbó los dos servicios en producción: la tabla
alembic_version de Postgres guarda version_num en VARCHAR(32), y Postgres
rechazó el UPDATE con "value too long for type character varying(32)" --
la migración completa (que corre en una sola transacción, ver
alembic/env.py: run_migrations_online) se revertía sola en cada arranque,
dejando la app sin levantar (502 "Application failed to respond") en bucle.
Se renombró a "0025_sr_condicion_accesorios" (28 caracteres) para que
quepa. Como la transacción se revertía completa, nunca llegó a tocar el
esquema real -- no hizo falta corregir datos, solo el nombre.

Revision ID: 0025_sr_condicion_accesorios
Revises: 0024_quita_mascota_asistente
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_sr_condicion_accesorios"
down_revision = "0024_quita_mascota_asistente"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("servicios_rapidos") as batch_op:
        batch_op.add_column(sa.Column("condicion", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("accesorios", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("servicios_rapidos") as batch_op:
        batch_op.drop_column("accesorios")
        batch_op.drop_column("condicion")
