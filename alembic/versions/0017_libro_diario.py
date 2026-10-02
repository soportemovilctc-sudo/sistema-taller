"""agrega el Libro Diario: catalogo de cuentas contables, asientos y sus
detalles Debe/Haber (contabilidad de partida doble). Corre en paralelo al
libro de caja de una sola entrada (movimientos_financieros) que ya existia,
sin modificarlo. Siembra el catalogo de cuentas inicial.

Revision ID: 0017_libro_diario
Revises: 0016_caja_roles
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_libro_diario"
down_revision = "0016_caja_roles"
branch_labels = None
depends_on = None

# codigo, nombre, tipo, naturaleza
CUENTAS_INICIALES = [
    ("1101", "Caja Chica (Fondo Fijo)", "activo", "deudora"),
    ("1102", "Banco (Caja General)", "activo", "deudora"),
    ("1103", "Cuentas por Cobrar Clientes", "activo", "deudora"),
    ("1104", "Cuentas por Cobrar Empleados", "activo", "deudora"),
    ("1105", "Crédito Fiscal ISV", "activo", "deudora"),
    ("2101", "Débito Fiscal ISV por Pagar", "pasivo", "acreedora"),
    ("4101", "Ventas", "ingreso", "acreedora"),
    ("4102", "Otros Ingresos (Sobrante de Caja)", "ingreso", "acreedora"),
    ("5101", "Gastos Operativos", "gasto", "deudora"),
]


def upgrade() -> None:
    op.create_table(
        "cuentas_contables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("codigo", sa.String(20), nullable=False, unique=True),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("naturaleza", sa.String(10), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "asientos_contables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("numero_asiento", sa.String(20), nullable=False, unique=True),
        sa.Column("fecha", sa.DateTime(), nullable=True),
        sa.Column("concepto", sa.String(255), nullable=False),
        sa.Column("tipo_evento", sa.String(40), nullable=False),
        sa.Column("referencia", sa.String(100), nullable=True),
        sa.Column("movimiento_financiero_id", sa.Integer(), sa.ForeignKey("movimientos_financieros.id"), nullable=True),
        sa.Column("usuario_nombre", sa.String(150), nullable=True),
    )
    op.create_index("ix_asientos_contables_fecha", "asientos_contables", ["fecha"])
    op.create_table(
        "detalles_asiento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asiento_id", sa.Integer(), sa.ForeignKey("asientos_contables.id"), nullable=False),
        sa.Column("cuenta_id", sa.Integer(), sa.ForeignKey("cuentas_contables.id"), nullable=False),
        sa.Column("debe", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("haber", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )

    cuentas_tabla = sa.table(
        "cuentas_contables",
        sa.column("codigo", sa.String),
        sa.column("nombre", sa.String),
        sa.column("tipo", sa.String),
        sa.column("naturaleza", sa.String),
        sa.column("activa", sa.Boolean),
    )
    op.bulk_insert(
        cuentas_tabla,
        [
            {"codigo": c, "nombre": n, "tipo": t, "naturaleza": nat, "activa": True}
            for c, n, t, nat in CUENTAS_INICIALES
        ],
    )


def downgrade() -> None:
    op.drop_table("detalles_asiento")
    op.drop_index("ix_asientos_contables_fecha", table_name="asientos_contables")
    op.drop_table("asientos_contables")
    op.drop_table("cuentas_contables")
