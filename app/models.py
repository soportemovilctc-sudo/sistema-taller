"""Modelos de base de datos (SQLAlchemy). Compatibles con SQLite y PostgreSQL."""
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, Date, DateTime, Boolean,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship

from app.database import Base

# ---------------------------------------------------------------------------
# Catálogos / constantes (se guardan como texto para no depender de ENUM de
# PostgreSQL y así poder usar SQLite en desarrollo sin fricciones).
# ---------------------------------------------------------------------------
TIPOS_EQUIPO = ["Celular", "Tablet", "Laptop", "PC", "Smartwatch", "Consola", "Otro"]

ESTADOS_ORDEN = [
    "RECIBIDO", "EN DIAGNOSTICO", "COTIZADO", "ESPERANDO APROBACION",
    "EN REPARACION", "LISTO PARA ENTREGAR", "ENTREGADO", "CANCELADO",
]

PRIORIDADES = ["Normal", "Alta", "Urgente"]

FORMAS_PAGO = ["Efectivo", "Transferencia", "Tarjeta", "Otro"]

ACCESORIOS_DISPONIBLES = [
    "Cargador", "Cable", "Estuche", "SIM", "Memoria", "Audífonos",
    "Batería externa", "Otro",
]

CONDICIONES_FISICAS = [
    "Pantalla", "Carcasa", "Cámaras", "Botones", "Puertos",
    "Golpes", "Rayones", "Piezas faltantes", "Daños visibles",
]

TIPOS_MOVIMIENTO_INVENTARIO = ["entrada", "salida", "ajuste"]
TIPOS_MOVIMIENTO_FINANCIERO = ["ingreso", "gasto"]


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    nombre_completo = Column(String(150), nullable=False)
    rol = Column(String(20), nullable=False, default="tecnico")  # admin | tecnico | vendedor
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)


class Tecnico(Base):
    __tablename__ = "tecnicos"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False)
    telefono = Column(String(30))
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)

    ordenes = relationship("OrdenServicio", back_populates="tecnico")


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False, index=True)
    telefono = Column(String(30), index=True)
    whatsapp = Column(String(30))
    dni = Column(String(30), index=True)
    rtn = Column(String(20), index=True)
    correo = Column(String(150))
    direccion = Column(String(255))
    notas = Column(Text)
    creado_en = Column(DateTime, default=datetime.utcnow)

    ordenes = relationship("OrdenServicio", back_populates="cliente", cascade="all,delete-orphan")
    ventas = relationship("Venta", back_populates="cliente")


class Configuracion(Base):
    """Fila única (id=1) con los datos del taller usados en toda la app y el PDF."""
    __tablename__ = "configuracion"

    id = Column(Integer, primary_key=True)
    nombre_taller = Column(String(150), default="Mi Taller")
    logo_path = Column(String(255), nullable=True)
    telefono = Column(String(30), default="")
    whatsapp = Column(String(30), default="")
    direccion = Column(String(255), default="")
    correo = Column(String(150), default="")
    moneda = Column(String(5), default="L")
    recargo_default_pct = Column(Numeric(6, 2), default=0)
    info_pdf_extra = Column(Text, default="")


class OrdenServicio(Base):
    __tablename__ = "ordenes_servicio"

    id = Column(Integer, primary_key=True)
    numero_orden = Column(String(20), unique=True, nullable=False, index=True)
    fecha = Column(DateTime, default=datetime.utcnow, nullable=False)

    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    tecnico_id = Column(Integer, ForeignKey("tecnicos.id"), nullable=True)

    tipo_equipo = Column(String(30), default="Celular")
    marca = Column(String(80))
    modelo = Column(String(80))
    imei = Column(String(50))
    numero_serie = Column(String(50))
    accesorios = Column(Text, default="")  # lista separada por comas

    condicion_fisica = Column(Text, default="")  # tags separados por comas
    observaciones_condicion = Column(Text, default="")
    falla_reportada = Column(Text, default="")
    diagnostico = Column(Text, default="")
    trabajo_realizado = Column(Text, default="")
    observaciones = Column(Text, default="")

    prioridad = Column(String(20), default="Normal")
    estado = Column(String(30), default="RECIBIDO", index=True)

    # Seguridad del dispositivo (dato sensible: no exponer en listados)
    pin = Column(String(20), nullable=True)
    patron = Column(String(50), nullable=True)  # ej: "1,2,3,6,9"

    # Financiero
    cotizacion = Column(Numeric(10, 2), default=0)
    recargo_pct = Column(Numeric(6, 2), default=0)
    recargo_monto = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(10, 2), default=0)
    abonado = Column(Numeric(10, 2), default=0)
    saldo = Column(Numeric(10, 2), default=0)
    forma_pago = Column(String(20), default="Efectivo")

    fecha_entrada = Column(Date, default=date.today)
    fecha_entrega = Column(Date, nullable=True)

    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="ordenes")
    tecnico = relationship("Tecnico", back_populates="ordenes")
    historial = relationship("HistorialEstado", back_populates="orden", cascade="all,delete-orphan", order_by="HistorialEstado.fecha")
    pagos = relationship("Pago", back_populates="orden", cascade="all,delete-orphan", order_by="Pago.fecha")
    facturas = relationship("Factura", back_populates="orden", order_by="Factura.id")

    def lista_accesorios(self):
        return [a for a in (self.accesorios or "").split(",") if a]

    def lista_condicion(self):
        return [c for c in (self.condicion_fisica or "").split(",") if c]


Index("ix_ordenes_marca_modelo", OrdenServicio.marca, OrdenServicio.modelo)


class HistorialEstado(Base):
    __tablename__ = "historial_estados"

    id = Column(Integer, primary_key=True)
    orden_id = Column(Integer, ForeignKey("ordenes_servicio.id"), nullable=False)
    estado_anterior = Column(String(30))
    estado_nuevo = Column(String(30), nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    usuario_nombre = Column(String(150))
    observacion = Column(Text, default="")

    orden = relationship("OrdenServicio", back_populates="historial")


class Pago(Base):
    """Abono registrado sobre una orden de servicio."""
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True)
    orden_id = Column(Integer, ForeignKey("ordenes_servicio.id"), nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    monto = Column(Numeric(10, 2), nullable=False)
    forma_pago = Column(String(20), default="Efectivo")
    usuario_nombre = Column(String(150))
    observacion = Column(Text, default="")

    orden = relationship("OrdenServicio", back_populates="pagos")


class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True)
    codigo = Column(String(50), unique=True, nullable=False, index=True)
    nombre = Column(String(150), nullable=False, index=True)
    categoria = Column(String(80))
    marca = Column(String(80))
    costo = Column(Numeric(10, 2), default=0)
    precio_venta = Column(Numeric(10, 2), default=0)
    existencia = Column(Integer, default=0)
    stock_minimo = Column(Integer, default=0)
    proveedor = Column(String(150))
    estado = Column(String(20), default="activo")  # activo | inactivo
    creado_en = Column(DateTime, default=datetime.utcnow)

    movimientos = relationship("MovimientoInventario", back_populates="producto", cascade="all,delete-orphan")


class MovimientoInventario(Base):
    __tablename__ = "movimientos_inventario"

    id = Column(Integer, primary_key=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    tipo = Column(String(20), nullable=False)  # entrada | salida | ajuste
    cantidad = Column(Integer, nullable=False)
    existencia_resultante = Column(Integer, nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    usuario_nombre = Column(String(150))
    motivo = Column(Text, default="")

    producto = relationship("Producto", back_populates="movimientos")


class Venta(Base):
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True)
    numero_venta = Column(String(20), unique=True, nullable=False, index=True)
    fecha = Column(DateTime, default=datetime.utcnow)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    subtotal = Column(Numeric(10, 2), default=0)
    descuento = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(10, 2), default=0)
    forma_pago = Column(String(20), default="Efectivo")
    monto_recibido = Column(Numeric(10, 2), default=0)
    cambio = Column(Numeric(10, 2), default=0)
    usuario_nombre = Column(String(150))

    cliente = relationship("Cliente", back_populates="ventas")
    detalles = relationship("DetalleVenta", back_populates="venta", cascade="all,delete-orphan")


class DetalleVenta(Base):
    __tablename__ = "detalle_ventas"

    id = Column(Integer, primary_key=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)

    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto")


class MovimientoFinanciero(Base):
    """Ingresos y gastos generales del taller (contabilidad)."""
    __tablename__ = "movimientos_financieros"

    id = Column(Integer, primary_key=True)
    tipo = Column(String(10), nullable=False)  # ingreso | gasto
    categoria = Column(String(80), nullable=False)
    monto = Column(Numeric(10, 2), nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow, index=True)
    descripcion = Column(Text, default="")
    usuario_nombre = Column(String(150))
    referencia = Column(String(100), default="")  # ej: "Orden OS-000001"


# ---------------------------------------------------------------------------
# Catálogo de marcas y modelos de equipos (celulares, tablets, laptops, etc.)
# ---------------------------------------------------------------------------
class MarcaEquipo(Base):
    __tablename__ = "marcas_equipo"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(80), unique=True, nullable=False, index=True)
    orden = Column(Integer, default=0)
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)

    modelos = relationship("ModeloEquipo", back_populates="marca", cascade="all,delete-orphan", order_by="ModeloEquipo.nombre")


class ModeloEquipo(Base):
    __tablename__ = "modelos_equipo"
    __table_args__ = (UniqueConstraint("marca_id", "nombre", name="uq_modelo_por_marca"),)

    id = Column(Integer, primary_key=True)
    marca_id = Column(Integer, ForeignKey("marcas_equipo.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)

    marca = relationship("MarcaEquipo", back_populates="modelos")


# ---------------------------------------------------------------------------
# Facturación: configuración (interna y fiscal SAR - Honduras) y documentos
# emitidos. Los datos fiscales (CAI, rango autorizado, RTN) los proporciona
# el usuario según la resolución que le entregue la SAR.
# ---------------------------------------------------------------------------
TIPOS_DOCUMENTO_FACTURA = ["interno", "fiscal"]


class ConfiguracionFacturacion(Base):
    """Fila única (id=1) con los parámetros de facturación interna y fiscal."""
    __tablename__ = "configuracion_facturacion"

    id = Column(Integer, primary_key=True)

    tipo_documento_default = Column(String(10), default="interno")  # interno | fiscal

    # --- Datos del emisor para la factura fiscal ---
    rtn_taller = Column(String(20), default="")
    razon_social = Column(String(200), default="")
    nombre_comercial = Column(String(200), default="")
    domicilio_fiscal = Column(Text, default="")

    # --- CAI y rango autorizado por la SAR ---
    cai = Column(String(50), default="")
    establecimiento = Column(String(10), default="001")
    punto_emision = Column(String(10), default="001")
    tipo_documento_codigo = Column(String(5), default="01")
    rango_autorizado_inicio = Column(String(30), default="")
    rango_autorizado_fin = Column(String(30), default="")
    fecha_limite_emision = Column(Date, nullable=True)
    correlativo_fiscal_actual = Column(Integer, default=0)

    # --- Impuesto (ISV Honduras) ---
    isv_tasa = Column(Numeric(5, 2), default=15)
    servicios_exentos_default = Column(Boolean, default=False)

    # --- Documento interno (comprobante, no válido ante la SAR) ---
    prefijo_interno = Column(String(20), default="REC")
    correlativo_interno_actual = Column(Integer, default=0)

    # --- Textos legales configurables que se imprimen en cada documento ---
    texto_legal_fiscal = Column(Text, default=(
        "Original: Cliente / Copia: Obligado Tributario. "
        "La factura es beneficio de todos, exíjala."
    ))
    texto_legal_interno = Column(Text, default=(
        "Este documento es un comprobante interno del taller y no es válido "
        "como factura fiscal ante la SAR."
    ))


class Factura(Base):
    """Documento de cobro (interno o fiscal) generado a partir de una orden
    de servicio. Una vez emitida una factura FISCAL no debe editarse ni
    borrarse: solo puede anularse, conservando el número consumido."""
    __tablename__ = "facturas"

    id = Column(Integer, primary_key=True)
    orden_id = Column(Integer, ForeignKey("ordenes_servicio.id"), nullable=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=True)

    tipo = Column(String(10), nullable=False)  # interno | fiscal
    numero_documento = Column(String(40), unique=True, nullable=False, index=True)
    correlativo = Column(Integer, nullable=False)

    # Snapshot de los datos fiscales vigentes al momento de emitir (para que
    # un cambio posterior en Configuración no altere documentos ya emitidos).
    cai_usado = Column(String(50), nullable=True)
    rango_autorizado_inicio = Column(String(30), nullable=True)
    rango_autorizado_fin = Column(String(30), nullable=True)
    fecha_limite_emision = Column(Date, nullable=True)
    rtn_emisor = Column(String(20), nullable=True)
    razon_social_emisor = Column(String(200), nullable=True)

    # Snapshot de los datos del cliente al momento de emitir.
    cliente_nombre = Column(String(150), default="")
    cliente_rtn = Column(String(20), default="")
    cliente_direccion = Column(String(255), default="")

    fecha_emision = Column(DateTime, default=datetime.utcnow)

    subtotal = Column(Numeric(10, 2), default=0)
    descuento = Column(Numeric(10, 2), default=0)
    importe_exento = Column(Numeric(10, 2), default=0)
    importe_gravado = Column(Numeric(10, 2), default=0)
    isv_tasa = Column(Numeric(5, 2), default=15)
    isv_monto = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(10, 2), default=0)

    anulada = Column(Boolean, default=False, nullable=False)
    motivo_anulacion = Column(Text, nullable=True)

    usuario_nombre = Column(String(150))
    creado_en = Column(DateTime, default=datetime.utcnow)

    orden = relationship("OrdenServicio", back_populates="facturas")
    venta = relationship("Venta")


class ServicioRapido(Base):
    """Plantilla de 'servicio rápido': un conjunto de datos predefinidos
    (falla, estado físico, observaciones, trabajo, plazo y precio) que el
    técnico puede aplicar con un clic al crear o editar una orden, en vez
    de escribir todo el diagnóstico a mano cada vez."""
    __tablename__ = "servicios_rapidos"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(120), nullable=False)

    falla_reportada = Column(Text, default="")
    estado_fisico = Column(Text, default="")
    observaciones = Column(Text, default="")
    trabajo_realizado = Column(Text, default="")

    dias_plazo = Column(Integer, default=0)
    cotizacion = Column(Numeric(10, 2), default=0)
    recargo_pct = Column(Numeric(6, 2), default=0)

    orden = Column(Integer, default=0)
    creado_en = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("nombre", name="uq_servicios_rapidos_nombre"),)

    def a_dict(self):
        return {
            "id": self.id,
            "nombre": self.nombre,
            "falla_reportada": self.falla_reportada or "",
            "estado_fisico": self.estado_fisico or "",
            "observaciones": self.observaciones or "",
            "trabajo_realizado": self.trabajo_realizado or "",
            "dias_plazo": self.dias_plazo or 0,
            "cotizacion": float(self.cotizacion or 0),
            "recargo_pct": float(self.recargo_pct or 0),
        }
