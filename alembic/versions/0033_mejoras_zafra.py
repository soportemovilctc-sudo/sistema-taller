"""Mejoras tomadas de Zafra: proveedores, cotizaciones, bitácora,
existencia máxima de productos y anulación de compras recibidas. Solo agrega tablas y columnas nuevas
(vacías); no toca datos existentes.

IMPORTANTE: revision ID de 32 caracteres o menos.

Revision ID: 0033_mejoras_zafra
Revises: 0032_historial_producto
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0033_mejoras_zafra"
down_revision = "0032_historial_producto"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proveedores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("rtn", sa.String(20), server_default=""),
        sa.Column("telefono", sa.String(30), server_default=""),
        sa.Column("whatsapp", sa.String(30), server_default=""),
        sa.Column("correo", sa.String(150), server_default=""),
        sa.Column("direccion", sa.String(255), server_default=""),
        sa.Column("contacto", sa.String(150), server_default=""),
        sa.Column("notas", sa.Text(), server_default=""),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_proveedores_nombre", "proveedores", ["nombre"])

    op.create_table(
        "cotizaciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("numero", sa.String(20), nullable=False, unique=True),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=True),
        sa.Column("cliente_nombre", sa.String(150), server_default=""),
        sa.Column("cliente_telefono", sa.String(30), server_default=""),
        sa.Column("validez_dias", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("notas", sa.Text(), server_default=""),
        sa.Column("estado", sa.String(12), nullable=False, server_default="vigente"),
        sa.Column("precios_con_isv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("isv", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("venta_id", sa.Integer(), sa.ForeignKey("ventas.id"), nullable=True),
        sa.Column("usuario_nombre", sa.String(150), server_default=""),
    )
    op.create_index("ix_cotizaciones_fecha", "cotizaciones", ["fecha"])
    op.create_table(
        "cotizaciones_detalle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cotizacion_id", sa.Integer(), sa.ForeignKey("cotizaciones.id"), nullable=False),
        sa.Column("producto_id", sa.Integer(), sa.ForeignKey("productos.id"), nullable=True),
        sa.Column("descripcion", sa.String(200), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("precio_unitario", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.create_index("ix_cotizaciones_detalle_cotizacion_id", "cotizaciones_detalle", ["cotizacion_id"])

    op.create_table(
        "bitacora",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("usuario_nombre", sa.String(150), server_default=""),
        sa.Column("usuario_rol", sa.String(20), server_default=""),
        sa.Column("modulo", sa.String(40), server_default=""),
        sa.Column("accion", sa.String(200), nullable=False),
        sa.Column("ruta", sa.String(255), server_default=""),
        sa.Column("enlace", sa.String(255), server_default=""),
        sa.Column("resultado", sa.String(10), server_default=""),
        sa.Column("ip", sa.String(60), server_default=""),
    )
    op.create_index("ix_bitacora_fecha", "bitacora", ["fecha"])

    with op.batch_alter_table("productos") as b:
        b.add_column(sa.Column("stock_maximo", sa.Integer(), nullable=True))
    with op.batch_alter_table("solicitudes_compra") as b:
        b.add_column(sa.Column("proveedor_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("recepciones_compra") as b:
        b.add_column(sa.Column("anulada", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("anulada_en", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("anulada_por", sa.String(150), nullable=True))
        b.add_column(sa.Column("motivo_anulacion", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recepciones_compra") as b:
        for c in ("motivo_anulacion", "anulada_por", "anulada_en", "anulada"):
            b.drop_column(c)
    with op.batch_alter_table("solicitudes_compra") as b:
        b.drop_column("proveedor_id")
    with op.batch_alter_table("productos") as b:
        b.drop_column("stock_maximo")
    op.drop_index("ix_bitacora_fecha", table_name="bitacora")
    op.drop_table("bitacora")
    op.drop_index("ix_cotizaciones_detalle_cotizacion_id", table_name="cotizaciones_detalle")
    op.drop_table("cotizaciones_detalle")
    op.drop_index("ix_cotizaciones_fecha", table_name="cotizaciones")
    op.drop_table("cotizaciones")
    op.drop_index("ix_proveedores_nombre", table_name="proveedores")
    op.drop_table("proveedores")
