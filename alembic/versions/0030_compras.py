"""Compras: solicitudes de compra y recepciones (con su detalle), el vínculo
del pago de una recepción en movimientos_financieros y el precio de lista
en el detalle de cada venta del Punto de Venta.
Solo agrega tablas y columnas nuevas (vacías); no toca ningún dato existente.

IMPORTANTE: revision ID de 32 caracteres o menos (ver la nota en
0025_sr_condicion_accesorios.py).

Revision ID: 0030_compras
Revises: 0029_partidas_balance
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0030_compras"
down_revision = "0029_partidas_balance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "solicitudes_compra",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("numero", sa.String(20), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("proveedor", sa.String(150), nullable=False, server_default=""),
        sa.Column("notas", sa.Text(), server_default=""),
        sa.Column("estado", sa.String(12), nullable=False, server_default="pendiente"),
        sa.Column("total_estimado", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("usuario_nombre", sa.String(150), server_default=""),
        sa.Column("cerrada_en", sa.DateTime(), nullable=True),
        sa.Column("cerrada_por", sa.String(150), nullable=True),
        sa.Column("motivo_cierre", sa.Text(), nullable=True),
    )
    op.create_index("ix_solicitudes_compra_numero", "solicitudes_compra", ["numero"], unique=True)
    op.create_index("ix_solicitudes_compra_fecha", "solicitudes_compra", ["fecha"])
    op.create_index("ix_solicitudes_compra_estado", "solicitudes_compra", ["estado"])

    op.create_table(
        "solicitudes_compra_detalle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("solicitud_id", sa.Integer(), sa.ForeignKey("solicitudes_compra.id"), nullable=False),
        sa.Column("producto_id", sa.Integer(), sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("cantidad_recibida", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("costo_unitario", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.create_index("ix_sc_detalle_solicitud", "solicitudes_compra_detalle", ["solicitud_id"])
    op.create_index("ix_sc_detalle_producto", "solicitudes_compra_detalle", ["producto_id"])

    op.create_table(
        "recepciones_compra",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("numero", sa.String(20), nullable=False),
        sa.Column("solicitud_id", sa.Integer(), sa.ForeignKey("solicitudes_compra.id"), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("proveedor", sa.String(150), server_default=""),
        sa.Column("factura_proveedor", sa.String(60), server_default=""),
        sa.Column("forma_pago", sa.String(12), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("isv", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("pagado", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("notas", sa.Text(), server_default=""),
        sa.Column("usuario_nombre", sa.String(150), server_default=""),
    )
    op.create_index("ix_recepciones_compra_numero", "recepciones_compra", ["numero"], unique=True)
    op.create_index("ix_recepciones_compra_solicitud", "recepciones_compra", ["solicitud_id"])
    op.create_index("ix_recepciones_compra_fecha", "recepciones_compra", ["fecha"])

    op.create_table(
        "recepciones_compra_detalle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recepcion_id", sa.Integer(), sa.ForeignKey("recepciones_compra.id"), nullable=False),
        sa.Column("producto_id", sa.Integer(), sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("costo_unitario", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("existencia_anterior", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("costo_anterior", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("costo_nuevo", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.create_index("ix_rc_detalle_recepcion", "recepciones_compra_detalle", ["recepcion_id"])
    op.create_index("ix_rc_detalle_producto", "recepciones_compra_detalle", ["producto_id"])

    with op.batch_alter_table("movimientos_financieros") as batch_op:
        batch_op.add_column(sa.Column("recepcion_compra_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_movimientos_financieros_recepcion_compra_id", ["recepcion_compra_id"])
    with op.batch_alter_table("detalle_ventas") as batch_op:
        batch_op.add_column(sa.Column("precio_lista", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("detalle_ventas") as batch_op:
        batch_op.drop_column("precio_lista")
    with op.batch_alter_table("movimientos_financieros") as batch_op:
        batch_op.drop_index("ix_movimientos_financieros_recepcion_compra_id")
        batch_op.drop_column("recepcion_compra_id")
    for idx, tabla in (("ix_rc_detalle_producto", "recepciones_compra_detalle"), ("ix_rc_detalle_recepcion", "recepciones_compra_detalle")):
        op.drop_index(idx, table_name=tabla)
    op.drop_table("recepciones_compra_detalle")
    for idx in ("ix_recepciones_compra_fecha", "ix_recepciones_compra_solicitud", "ix_recepciones_compra_numero"):
        op.drop_index(idx, table_name="recepciones_compra")
    op.drop_table("recepciones_compra")
    for idx in ("ix_sc_detalle_producto", "ix_sc_detalle_solicitud"):
        op.drop_index(idx, table_name="solicitudes_compra_detalle")
    op.drop_table("solicitudes_compra_detalle")
    for idx in ("ix_solicitudes_compra_estado", "ix_solicitudes_compra_fecha", "ix_solicitudes_compra_numero"):
        op.drop_index(idx, table_name="solicitudes_compra")
    op.drop_table("solicitudes_compra")
