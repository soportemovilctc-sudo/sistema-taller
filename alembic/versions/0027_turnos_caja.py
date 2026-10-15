"""Apertura y cierre de caja (turnos).

Agrega:
  - turnos_caja: cada apertura de caja con su efectivo inicial y, al
    cerrarla, el arqueo (efectivo esperado, contado y diferencia).
  - turnos_caja_eventos: bitácora de cada turno (apertura, cierre,
    reapertura y ediciones: quién, cuándo y qué cambió).
  - turno_caja_id en pagos, movimientos_financieros, ventas y facturas:
    a qué turno pertenece cada registro NUEVO. Es una columna vacía (NULL)
    para todo lo que ya existía: no se toca ningún dato del registro
    contable anterior.
  - configuracion.caja_obligatoria_desde: desde cuándo es obligatorio tener
    la caja abierta para cobrar/abonar/facturar/vender. Se programa para el
    viernes 16/10/2026 a las 6:00 a.m. hora de Honduras (12:00 UTC), como
    pidió Ricardo, para que la cajera termine su turno de hoy sin cambios.

IMPORTANTE: el revision ID debe tener 32 caracteres o menos (la columna
alembic_version.version_num de Postgres es VARCHAR(32); ver la nota en
0025_sr_condicion_accesorios.py).

Revision ID: 0027_turnos_caja
Revises: 0026_revierte_sr_cond_acc
Create Date: 2026-10-15
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "0027_turnos_caja"
down_revision = "0026_revierte_sr_cond_acc"
branch_labels = None
depends_on = None

TABLAS_CON_TURNO = ("pagos", "movimientos_financieros", "ventas", "facturas")

# 16/10/2026 06:00 en Honduras (UTC-6) = 16/10/2026 12:00 UTC.
CAJA_OBLIGATORIA_DESDE_UTC = datetime(2026, 10, 16, 12, 0, 0)


def upgrade() -> None:
    op.create_table(
        "turnos_caja",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("estado", sa.String(10), nullable=False, server_default="abierta"),
        sa.Column("fecha_apertura", sa.DateTime(), nullable=False),
        sa.Column("abierta_por", sa.String(150), server_default=""),
        sa.Column("monto_inicial", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("notas_apertura", sa.Text(), server_default=""),
        sa.Column("fecha_cierre", sa.DateTime(), nullable=True),
        sa.Column("cerrada_por", sa.String(150), nullable=True),
        sa.Column("efectivo_esperado", sa.Numeric(10, 2), nullable=True),
        sa.Column("efectivo_contado", sa.Numeric(10, 2), nullable=True),
        sa.Column("diferencia", sa.Numeric(10, 2), nullable=True),
        sa.Column("notas_cierre", sa.Text(), server_default=""),
        sa.Column("cerrada_tarde", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_turnos_caja_estado", "turnos_caja", ["estado"])
    op.create_index("ix_turnos_caja_fecha_apertura", "turnos_caja", ["fecha_apertura"])

    op.create_table(
        "turnos_caja_eventos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("turno_id", sa.Integer(), sa.ForeignKey("turnos_caja.id"), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("accion", sa.String(20), nullable=False),
        sa.Column("usuario_nombre", sa.String(150), server_default=""),
        sa.Column("detalle", sa.Text(), server_default=""),
    )
    op.create_index("ix_turnos_caja_eventos_turno_id", "turnos_caja_eventos", ["turno_id"])

    # Columna nueva, vacía, sin llave foránea a nivel de base de datos (solo
    # un índice): agregarla no toca ni bloquea los datos que ya existen.
    for tabla in TABLAS_CON_TURNO:
        with op.batch_alter_table(tabla) as batch_op:
            batch_op.add_column(sa.Column("turno_caja_id", sa.Integer(), nullable=True))
        op.create_index(f"ix_{tabla}_turno_caja_id", tabla, ["turno_caja_id"])

    with op.batch_alter_table("configuracion") as batch_op:
        batch_op.add_column(sa.Column("caja_obligatoria_desde", sa.DateTime(), nullable=True))

    # Literal SQL (no parámetro) para que sea idéntico en Postgres y SQLite,
    # y en el SQL que genera "alembic upgrade --sql" para probarlo.
    op.execute(
        "UPDATE configuracion SET caja_obligatoria_desde = "
        f"'{CAJA_OBLIGATORIA_DESDE_UTC.strftime('%Y-%m-%d %H:%M:%S')}' WHERE id = 1"
    )


def downgrade() -> None:
    with op.batch_alter_table("configuracion") as batch_op:
        batch_op.drop_column("caja_obligatoria_desde")
    for tabla in TABLAS_CON_TURNO:
        op.drop_index(f"ix_{tabla}_turno_caja_id", table_name=tabla)
        with op.batch_alter_table(tabla) as batch_op:
            batch_op.drop_column("turno_caja_id")
    op.drop_index("ix_turnos_caja_eventos_turno_id", table_name="turnos_caja_eventos")
    op.drop_table("turnos_caja_eventos")
    op.drop_index("ix_turnos_caja_fecha_apertura", table_name="turnos_caja")
    op.drop_index("ix_turnos_caja_estado", table_name="turnos_caja")
    op.drop_table("turnos_caja")
