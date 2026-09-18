"""facturacion (interna y fiscal SAR) + catalogo de marcas y modelos + rtn cliente

Revision ID: 0002_facturacion_catalogo
Revises: 0001_initial
Create Date: 2026-09-18

"""
from alembic import op
import sqlalchemy as sa

revision = "0002_facturacion_catalogo"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- RTN del cliente (necesario para facturas fiscales) ---
    op.add_column("clientes", sa.Column("rtn", sa.String(20), nullable=True))
    op.create_index("ix_clientes_rtn", "clientes", ["rtn"])

    # --- Catálogo de marcas y modelos ---
    op.create_table(
        "marcas_equipo",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("orden", sa.Integer, server_default="0"),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime, nullable=True),
        sa.UniqueConstraint("nombre", name="uq_marcas_nombre"),
    )
    op.create_index("ix_marcas_nombre", "marcas_equipo", ["nombre"])

    op.create_table(
        "modelos_equipo",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("marca_id", sa.Integer, sa.ForeignKey("marcas_equipo.id"), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime, nullable=True),
        sa.UniqueConstraint("marca_id", "nombre", name="uq_modelo_por_marca"),
    )

    # --- Configuración de facturación (fila única id=1) ---
    op.create_table(
        "configuracion_facturacion",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tipo_documento_default", sa.String(10), server_default="interno"),
        sa.Column("rtn_taller", sa.String(20), server_default=""),
        sa.Column("razon_social", sa.String(200), server_default=""),
        sa.Column("nombre_comercial", sa.String(200), server_default=""),
        sa.Column("domicilio_fiscal", sa.Text, server_default=""),
        sa.Column("cai", sa.String(50), server_default=""),
        sa.Column("establecimiento", sa.String(10), server_default="001"),
        sa.Column("punto_emision", sa.String(10), server_default="001"),
        sa.Column("tipo_documento_codigo", sa.String(5), server_default="01"),
        sa.Column("rango_autorizado_inicio", sa.String(30), server_default=""),
        sa.Column("rango_autorizado_fin", sa.String(30), server_default=""),
        sa.Column("fecha_limite_emision", sa.Date, nullable=True),
        sa.Column("correlativo_fiscal_actual", sa.Integer, server_default="0"),
        sa.Column("isv_tasa", sa.Numeric(5, 2), server_default="15"),
        sa.Column("servicios_exentos_default", sa.Boolean, server_default=sa.false()),
        sa.Column("prefijo_interno", sa.String(20), server_default="REC"),
        sa.Column("correlativo_interno_actual", sa.Integer, server_default="0"),
        sa.Column("texto_legal_fiscal", sa.Text, server_default=""),
        sa.Column("texto_legal_interno", sa.Text, server_default=""),
    )

    # --- Facturas (documentos de cobro emitidos) ---
    op.create_table(
        "facturas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("orden_id", sa.Integer, sa.ForeignKey("ordenes_servicio.id"), nullable=True),
        sa.Column("venta_id", sa.Integer, sa.ForeignKey("ventas.id"), nullable=True),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("numero_documento", sa.String(40), nullable=False),
        sa.Column("correlativo", sa.Integer, nullable=False),
        sa.Column("cai_usado", sa.String(50), nullable=True),
        sa.Column("rango_autorizado_inicio", sa.String(30), nullable=True),
        sa.Column("rango_autorizado_fin", sa.String(30), nullable=True),
        sa.Column("fecha_limite_emision", sa.Date, nullable=True),
        sa.Column("rtn_emisor", sa.String(20), nullable=True),
        sa.Column("razon_social_emisor", sa.String(200), nullable=True),
        sa.Column("cliente_nombre", sa.String(150), server_default=""),
        sa.Column("cliente_rtn", sa.String(20), server_default=""),
        sa.Column("cliente_direccion", sa.String(255), server_default=""),
        sa.Column("fecha_emision", sa.DateTime, nullable=True),
        sa.Column("subtotal", sa.Numeric(10, 2), server_default="0"),
        sa.Column("descuento", sa.Numeric(10, 2), server_default="0"),
        sa.Column("importe_exento", sa.Numeric(10, 2), server_default="0"),
        sa.Column("importe_gravado", sa.Numeric(10, 2), server_default="0"),
        sa.Column("isv_tasa", sa.Numeric(5, 2), server_default="15"),
        sa.Column("isv_monto", sa.Numeric(10, 2), server_default="0"),
        sa.Column("total", sa.Numeric(10, 2), server_default="0"),
        sa.Column("anulada", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("motivo_anulacion", sa.Text, nullable=True),
        sa.Column("usuario_nombre", sa.String(150)),
        sa.Column("creado_en", sa.DateTime, nullable=True),
        sa.UniqueConstraint("numero_documento", name="uq_facturas_numero_documento"),
    )
    op.create_index("ix_facturas_numero_documento", "facturas", ["numero_documento"])


def downgrade() -> None:
    op.drop_table("facturas")
    op.drop_table("configuracion_facturacion")
    op.drop_table("modelos_equipo")
    op.drop_table("marcas_equipo")
    op.drop_index("ix_clientes_rtn", table_name="clientes")
    op.drop_column("clientes", "rtn")
