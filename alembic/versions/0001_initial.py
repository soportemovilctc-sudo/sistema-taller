"""esquema inicial completo del sistema de taller

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-17

"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("nombre_completo", sa.String(150), nullable=False),
        sa.Column("rol", sa.String(20), nullable=False, server_default="tecnico"),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime, nullable=True),
        sa.UniqueConstraint("username", name="uq_usuarios_username"),
    )
    op.create_index("ix_usuarios_username", "usuarios", ["username"])

    op.create_table(
        "tecnicos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("telefono", sa.String(30)),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime, nullable=True),
    )

    op.create_table(
        "clientes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("telefono", sa.String(30)),
        sa.Column("whatsapp", sa.String(30)),
        sa.Column("dni", sa.String(30)),
        sa.Column("correo", sa.String(150)),
        sa.Column("direccion", sa.String(255)),
        sa.Column("notas", sa.Text),
        sa.Column("creado_en", sa.DateTime, nullable=True),
    )
    op.create_index("ix_clientes_nombre", "clientes", ["nombre"])
    op.create_index("ix_clientes_telefono", "clientes", ["telefono"])
    op.create_index("ix_clientes_dni", "clientes", ["dni"])

    op.create_table(
        "configuracion",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre_taller", sa.String(150), server_default="Mi Taller"),
        sa.Column("logo_path", sa.String(255), nullable=True),
        sa.Column("telefono", sa.String(30), server_default=""),
        sa.Column("whatsapp", sa.String(30), server_default=""),
        sa.Column("direccion", sa.String(255), server_default=""),
        sa.Column("correo", sa.String(150), server_default=""),
        sa.Column("moneda", sa.String(5), server_default="L"),
        sa.Column("recargo_default_pct", sa.Numeric(6, 2), server_default="0"),
        sa.Column("info_pdf_extra", sa.Text, server_default=""),
    )

    op.create_table(
        "ordenes_servicio",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("numero_orden", sa.String(20), nullable=False),
        sa.Column("fecha", sa.DateTime, nullable=False),
        sa.Column("cliente_id", sa.Integer, sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("tecnico_id", sa.Integer, sa.ForeignKey("tecnicos.id"), nullable=True),
        sa.Column("tipo_equipo", sa.String(30), server_default="Celular"),
        sa.Column("marca", sa.String(80)),
        sa.Column("modelo", sa.String(80)),
        sa.Column("imei", sa.String(50)),
        sa.Column("numero_serie", sa.String(50)),
        sa.Column("accesorios", sa.Text, server_default=""),
        sa.Column("condicion_fisica", sa.Text, server_default=""),
        sa.Column("observaciones_condicion", sa.Text, server_default=""),
        sa.Column("falla_reportada", sa.Text, server_default=""),
        sa.Column("diagnostico", sa.Text, server_default=""),
        sa.Column("trabajo_realizado", sa.Text, server_default=""),
        sa.Column("observaciones", sa.Text, server_default=""),
        sa.Column("prioridad", sa.String(20), server_default="Normal"),
        sa.Column("estado", sa.String(30), server_default="RECIBIDO"),
        sa.Column("pin", sa.String(20), nullable=True),
        sa.Column("patron", sa.String(50), nullable=True),
        sa.Column("cotizacion", sa.Numeric(10, 2), server_default="0"),
        sa.Column("recargo_pct", sa.Numeric(6, 2), server_default="0"),
        sa.Column("recargo_monto", sa.Numeric(10, 2), server_default="0"),
        sa.Column("total", sa.Numeric(10, 2), server_default="0"),
        sa.Column("abonado", sa.Numeric(10, 2), server_default="0"),
        sa.Column("saldo", sa.Numeric(10, 2), server_default="0"),
        sa.Column("forma_pago", sa.String(20), server_default="Efectivo"),
        sa.Column("fecha_entrada", sa.Date, nullable=True),
        sa.Column("fecha_entrega", sa.Date, nullable=True),
        sa.Column("creado_en", sa.DateTime, nullable=True),
        sa.Column("actualizado_en", sa.DateTime, nullable=True),
        sa.UniqueConstraint("numero_orden", name="uq_ordenes_numero_orden"),
    )
    op.create_index("ix_ordenes_numero_orden", "ordenes_servicio", ["numero_orden"])
    op.create_index("ix_ordenes_estado", "ordenes_servicio", ["estado"])
    op.create_index("ix_ordenes_marca_modelo", "ordenes_servicio", ["marca", "modelo"])

    op.create_table(
        "historial_estados",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("orden_id", sa.Integer, sa.ForeignKey("ordenes_servicio.id"), nullable=False),
        sa.Column("estado_anterior", sa.String(30)),
        sa.Column("estado_nuevo", sa.String(30), nullable=False),
        sa.Column("fecha", sa.DateTime, nullable=True),
        sa.Column("usuario_nombre", sa.String(150)),
        sa.Column("observacion", sa.Text, server_default=""),
    )

    op.create_table(
        "pagos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("orden_id", sa.Integer, sa.ForeignKey("ordenes_servicio.id"), nullable=False),
        sa.Column("fecha", sa.DateTime, nullable=True),
        sa.Column("monto", sa.Numeric(10, 2), nullable=False),
        sa.Column("forma_pago", sa.String(20), server_default="Efectivo"),
        sa.Column("usuario_nombre", sa.String(150)),
        sa.Column("observacion", sa.Text, server_default=""),
    )

    op.create_table(
        "productos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("codigo", sa.String(50), nullable=False),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("categoria", sa.String(80)),
        sa.Column("marca", sa.String(80)),
        sa.Column("costo", sa.Numeric(10, 2), server_default="0"),
        sa.Column("precio_venta", sa.Numeric(10, 2), server_default="0"),
        sa.Column("existencia", sa.Integer, server_default="0"),
        sa.Column("stock_minimo", sa.Integer, server_default="0"),
        sa.Column("proveedor", sa.String(150)),
        sa.Column("estado", sa.String(20), server_default="activo"),
        sa.Column("creado_en", sa.DateTime, nullable=True),
        sa.UniqueConstraint("codigo", name="uq_productos_codigo"),
    )
    op.create_index("ix_productos_codigo", "productos", ["codigo"])
    op.create_index("ix_productos_nombre", "productos", ["nombre"])

    op.create_table(
        "movimientos_inventario",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("cantidad", sa.Integer, nullable=False),
        sa.Column("existencia_resultante", sa.Integer, nullable=False),
        sa.Column("fecha", sa.DateTime, nullable=True),
        sa.Column("usuario_nombre", sa.String(150)),
        sa.Column("motivo", sa.Text, server_default=""),
    )

    op.create_table(
        "ventas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("numero_venta", sa.String(20), nullable=False),
        sa.Column("fecha", sa.DateTime, nullable=True),
        sa.Column("cliente_id", sa.Integer, sa.ForeignKey("clientes.id"), nullable=True),
        sa.Column("subtotal", sa.Numeric(10, 2), server_default="0"),
        sa.Column("descuento", sa.Numeric(10, 2), server_default="0"),
        sa.Column("total", sa.Numeric(10, 2), server_default="0"),
        sa.Column("forma_pago", sa.String(20), server_default="Efectivo"),
        sa.Column("monto_recibido", sa.Numeric(10, 2), server_default="0"),
        sa.Column("cambio", sa.Numeric(10, 2), server_default="0"),
        sa.Column("usuario_nombre", sa.String(150)),
        sa.UniqueConstraint("numero_venta", name="uq_ventas_numero_venta"),
    )
    op.create_index("ix_ventas_numero_venta", "ventas", ["numero_venta"])

    op.create_table(
        "detalle_ventas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("venta_id", sa.Integer, sa.ForeignKey("ventas.id"), nullable=False),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("productos.id"), nullable=False),
        sa.Column("cantidad", sa.Integer, nullable=False),
        sa.Column("precio_unitario", sa.Numeric(10, 2), nullable=False),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=False),
    )

    op.create_table(
        "movimientos_financieros",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("categoria", sa.String(80), nullable=False),
        sa.Column("monto", sa.Numeric(10, 2), nullable=False),
        sa.Column("fecha", sa.DateTime, nullable=True),
        sa.Column("descripcion", sa.Text, server_default=""),
        sa.Column("usuario_nombre", sa.String(150)),
        sa.Column("referencia", sa.String(100), server_default=""),
    )
    op.create_index("ix_movimientos_financieros_fecha", "movimientos_financieros", ["fecha"])


def downgrade() -> None:
    op.drop_table("movimientos_financieros")
    op.drop_table("detalle_ventas")
    op.drop_table("ventas")
    op.drop_table("movimientos_inventario")
    op.drop_table("productos")
    op.drop_table("pagos")
    op.drop_table("historial_estados")
    op.drop_table("ordenes_servicio")
    op.drop_table("configuracion")
    op.drop_table("clientes")
    op.drop_table("tecnicos")
    op.drop_table("usuarios")
