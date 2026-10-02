"""agrega el modulo de Caja: apertura/cierre, conciliacion bancaria y
egresos mayores. Extiende movimientos_financieros con cuenta (caja_chica |
banco), metodo_pago, cliente_nombre, num_referencia, comprobante adjunto y
estado de conciliacion; agrega tabla saldos_iniciales_mensuales para los
saldos con que arranca cada mes la Caja Chica y el Banco.

Revision ID: 0016_caja_roles
Revises: 0015_servicios
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_caja_roles"
down_revision = "0015_servicios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "movimientos_financieros",
        sa.Column("cuenta", sa.String(20), nullable=False, server_default="caja_chica"),
    )
    op.add_column("movimientos_financieros", sa.Column("metodo_pago", sa.String(30), nullable=True))
    op.add_column("movimientos_financieros", sa.Column("cliente_nombre", sa.String(150), nullable=True))
    op.add_column("movimientos_financieros", sa.Column("num_referencia", sa.String(60), nullable=True))
    op.add_column("movimientos_financieros", sa.Column("comprobante_data", sa.LargeBinary(), nullable=True))
    op.add_column("movimientos_financieros", sa.Column("comprobante_mime", sa.String(50), nullable=True))
    op.add_column("movimientos_financieros", sa.Column("estado_conciliacion", sa.String(20), nullable=True))
    op.add_column("movimientos_financieros", sa.Column("conciliado_por", sa.String(150), nullable=True))
    op.add_column("movimientos_financieros", sa.Column("conciliado_en", sa.DateTime(), nullable=True))

    op.create_table(
        "saldos_iniciales_mensuales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("saldo_inicial_caja_chica", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("saldo_inicial_banco", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("usuario_nombre", sa.String(150), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("anio", "mes", name="uq_saldo_inicial_anio_mes"),
    )


def downgrade() -> None:
    op.drop_table("saldos_iniciales_mensuales")
    op.drop_column("movimientos_financieros", "conciliado_en")
    op.drop_column("movimientos_financieros", "conciliado_por")
    op.drop_column("movimientos_financieros", "estado_conciliacion")
    op.drop_column("movimientos_financieros", "comprobante_mime")
    op.drop_column("movimientos_financieros", "comprobante_data")
    op.drop_column("movimientos_financieros", "num_referencia")
    op.drop_column("movimientos_financieros", "cliente_nombre")
    op.drop_column("movimientos_financieros", "metodo_pago")
    op.drop_column("movimientos_financieros", "cuenta")
