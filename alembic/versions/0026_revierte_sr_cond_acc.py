"""Revierte 0025: Ricardo pidió deshacer las 3 mejoras de "hacer una orden
más fácil" (orden de Marca/Modelo por historial, botón "Sin daños
visibles" y que Servicio rápido marque Condición/Accesorios) y dejar el
formulario de crear orden exactamente como estaba antes.

Esta migración SOLO deshace el cambio de esquema de 0025 (quita las
columnas condicion/accesorios de servicios_rapidos). El código de
app/models.py, app/routers/ordenes.py, app/routers/servicio_rapido.py,
app/templates/ordenes/form.html y app/static/js/orden.js vuelve en este
mismo commit a ser exactamente el de antes de 0025.

Se agrega una migración nueva en vez de borrar 0025 porque, para cuando
Ricardo pidió el cambio, ya pudo haber corrido en producción (Railway) y
quedar la base de datos marcada en esa revisión -- borrar el archivo de
0025 habría dejado esa marca "huérfana" (alembic no encuentra el script)
y tumbado el arranque de la app. Agregar 0026 es seguro en los dos casos:
si una base de datos nunca llegó a aplicar 0025, al llegar a "head" aplica
0025 y 0026 seguidas (agrega y enseguida quita las columnas, sin dejar
rastro); si ya estaba en 0025, solo aplica 0026 (quita las columnas).

NOTA: este archivo se llamó originalmente
"0026_revierte_condicion_accesorios_servicio_rapido" (revision ID de 50
caracteres), igual que el 0025 original -- ver la nota en
0025_sr_condicion_accesorios.py: ambos nombres largos tumbaron los dos
servicios en producción porque no caben en el VARCHAR(32) de
alembic_version.version_num en Postgres. Se renombró a
"0026_revierte_sr_cond_acc" (25 caracteres).

Revision ID: 0026_revierte_sr_cond_acc
Revises: 0025_sr_condicion_accesorios
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_revierte_sr_cond_acc"
down_revision = "0025_sr_condicion_accesorios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("servicios_rapidos") as batch_op:
        batch_op.drop_column("accesorios")
        batch_op.drop_column("condicion")


def downgrade() -> None:
    with op.batch_alter_table("servicios_rapidos") as batch_op:
        batch_op.add_column(sa.Column("condicion", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("accesorios", sa.Text(), nullable=False, server_default=""))
