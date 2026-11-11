"""Comisión del POS por cobros con tarjeta: porcentaje (3.8%) y desde cuándo
se descuenta (desde que se instala esta versión; lo anterior no se toca), y
el vínculo de cada comisión con su cobro.

IMPORTANTE: revision ID de 32 caracteres o menos.

Revision ID: 0040_comision_tarjeta
Revises: 0039_egresos
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0040_comision_tarjeta"
down_revision = "0039_egresos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("configuracion_facturacion") as b:
        b.add_column(sa.Column("comision_tarjeta_pct", sa.Numeric(5, 2), nullable=True))
        b.add_column(sa.Column("comision_tarjeta_desde", sa.DateTime(), nullable=True))
    # Desde ahora en adelante (hora del servidor en UTC, igual que las fechas de los movimientos).
    ahora = "(now() at time zone 'utc')" if op.get_bind().dialect.name == "postgresql" else "CURRENT_TIMESTAMP"
    op.execute(f"UPDATE configuracion_facturacion SET comision_tarjeta_pct = 3.80, comision_tarjeta_desde = {ahora}")
    with op.batch_alter_table("movimientos_financieros") as b:
        b.add_column(sa.Column("comision_de_id", sa.Integer(),
                               sa.ForeignKey("movimientos_financieros.id", name="fk_mov_comision_de"), nullable=True))
        b.create_index("ix_movimientos_financieros_comision_de_id", ["comision_de_id"])


def downgrade() -> None:
    with op.batch_alter_table("movimientos_financieros") as b:
        b.drop_index("ix_movimientos_financieros_comision_de_id")
        b.drop_column("comision_de_id")
    with op.batch_alter_table("configuracion_facturacion") as b:
        b.drop_column("comision_tarjeta_desde")
        b.drop_column("comision_tarjeta_pct")
