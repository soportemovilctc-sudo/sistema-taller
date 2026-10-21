"""Modelos de base de datos (SQLAlchemy). Compatibles con SQLite y PostgreSQL."""
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, Date, DateTime, Boolean,
    ForeignKey, UniqueConstraint, Index, LargeBinary
)
from sqlalchemy.orm import relationship

from app.database import Base

# ---------------------------------------------------------------------------
# Catálogos / constantes (se guardan como texto para no depender de ENUM de
# PostgreSQL y así poder usar SQLite en desarrollo sin fricciones).
# ---------------------------------------------------------------------------
TIPOS_EQUIPO = ["Celular", "Tablet", "Laptop", "PC", "Smartwatch", "Consola", "Otro"]

# Honduras no observa horario de verano: UTC-6 fijo. Se usa para que el
# contador de dias en el taller cambie a la medianoche local, no cada 24h
# exactas desde la hora de creacion.
HN_TZ = timezone(timedelta(hours=-6))

ESTADOS_ORDEN = [
    "RECIBIDO", "EN DIAGNOSTICO", "COTIZADO", "ESPERANDO APROBACION",
    "EN REPARACION", "LISTO PARA ENTREGAR", "ENTREGADO", "CANCELADO",
]

PRIORIDADES = ["Normal", "Alta", "Urgente"]

FORMAS_PAGO = ["Efectivo", "Transferencia", "Tarjeta", "Otro"]

# ---------------------------------------------------------------------------
# Módulo de Caja (apertura/cierre, conciliación bancaria, egresos mayores).
# ---------------------------------------------------------------------------
# Métodos de cobro que puede registrar la vista Cajera. "Tarjeta (POS)" se
# mantiene como texto distinto de "Tarjeta" (FORMAS_PAGO, usado en Órdenes)
# porque aquí nunca requiere referencia/comprobante, a diferencia de
# Transferencia.
METODOS_PAGO_CAJA = ["Efectivo", "Transferencia", "Tarjeta (POS)"]

# Categorías para "Gestión de Egresos Mayores" (vista Administrador): pagos
# con cargo directo a la cuenta bancaria, distintos de los gastos de caja
# chica que ya existían en Contabilidad.
CATEGORIAS_EGRESO_MAYOR = ["Proveedores", "Planillas", "Servicios", "Compras", "Otros"]

# Categoría de ingresos de caja chica que la Cajera puede registrar sin que
# vengan de un cobro con método de pago (ej. dinero encontrado, un reembolso
# recibido en efectivo, un ingreso que no corresponde a una orden).
CATEGORIA_OTRO_INGRESO_CAJA = "Otros ingresos"

# Categorías de "Salida de caja" (vista Cajera): egresos de efectivo del día
# a día, detallados uno por uno — equivalente a las columnas "Salidas de
# caja" y "Crédito por Garantía" de la hoja de cálculo original. Son egresos
# de caja chica (efectivo físico), distintos de los Egresos Mayores del
# Administrador (que siempre son contra la cuenta bancaria).
CATEGORIA_DEPOSITO_BANCO = "Depósito bancario"
CATEGORIA_NOMINA_EFECTIVO = "Nómina en efectivo"
# Los ingresos y egresos varios se registran SOLO desde Caja (ya no desde
# Reportes ni Contabilidad), para que siempre queden en la caja abierta.
# "Compras" y "Proveedores" son compras de mercadería: los Estados
# Financieros las usan para el costo de ventas.
CATEGORIAS_SALIDA_CAJA = [
    "Salida de caja", "Compra menor", "Compras", "Proveedores", "Servicios básicos",
    "Transporte", "Crédito por garantía", "Otro gasto de caja",
    CATEGORIA_DEPOSITO_BANCO, CATEGORIA_NOMINA_EFECTIVO,
]

# Ingreso contable de una Orden: ANTES se generaba dos veces (al agregar el
# repuesto/servicio a la orden, y otra vez al cobrarlo con un abono o al
# entregar el equipo), lo que duplicaba Ingresos/Caja/Utilidad Neta. Ahora
# el ÚNICO momento que genera este ingreso es cuando se emite una Factura
# (interna o fiscal) para la orden (ver app/routers/facturacion.py). Las
# categorías viejas (CATEGORIAS_ORDEN_EXCLUIDAS_CONTABILIDAD) ya no se
# vuelven a generar, pero sus filas existentes NUNCA se borran — solo se
# marcan excluir_de_contabilidad=True (ver migración 0020) para que dejen
# de sumar en Ingresos/Caja/Utilidad Neta/Contabilidad.
CATEGORIA_VENTA_FACTURADA = "Venta facturada (orden)"
CATEGORIAS_ORDEN_EXCLUIDAS_CONTABILIDAD = [
    "Venta de repuesto (orden)", "Venta de servicio (orden)",
    "Abono de orden", "Cancelación de orden (automático)",
    "Reversión por orden cancelada",
    "Corrección de repuesto (orden)", "Corrección de servicio (orden)",
]

ACCESORIOS_DISPONIBLES = [
    "Cobertor", "Vidrio", "Micro SD", "S Pen", "SIM tipo", "SIM Claro",
]

CONDICIONES_FISICAS = [
    "Sin daños visibles", "Apagado", "Pantalla dañada", "Housing dañado",
    "Batería dañada", "Se reinicia", "Mojado",
]

# Apariencia personal (ver Usuario.tema_modo / tema_acento / mascota y la
# página "Apariencia" en auth.py).
TEMAS_MODO = ["oscuro", "claro", "vidrio"]
TEMAS_ACENTO = [
    {"valor": "azul", "nombre": "Azul clásico (el de siempre)", "muestra": "#2563eb"},
    {"valor": "cian", "nombre": "Cian tecnológico", "muestra": "#0891b2"},
    {"valor": "verde", "nombre": "Verde esmeralda", "muestra": "#059669"},
    {"valor": "purpura", "nombre": "Púrpura", "muestra": "#7c3aed"},
    {"valor": "naranja", "nombre": "Naranja", "muestra": "#ea580c"},
    {"valor": "rendimiento", "nombre": "Rojo alto rendimiento", "muestra": "#ED1C24"},
    {"valor": "personalizado", "nombre": "Personalizado (elige tu color)", "muestra": None},
]
MASCOTAS_DISPONIBLES = [
    {"valor": "panda", "nombre": "Panda"},
    {"valor": "leon", "nombre": "León"},
    {"valor": "raton", "nombre": "Ratón"},
    {"valor": "robot", "nombre": "Robot"},
]

# "Efectos de ventana" (ver Usuario.efecto_cierre_ventana y los demás
# campos de abajo): aproximaciones con CSS/JS de los efectos de
# minimizar/Dock/Liquid Glass de macOS, cada uno activable por separado.
EFECTOS_CIERRE_VENTANA = [
    {"valor": "escala", "nombre": "Escala (el de siempre)"},
    {"valor": "genie", "nombre": "Genie"},
    {"valor": "succion", "nombre": "Succión"},
    {"valor": "ninguno", "nombre": "Ninguno (cierre instantáneo)"},
]

TIPOS_MOVIMIENTO_INVENTARIO = ["entrada", "salida", "ajuste"]
TIPOS_MOVIMIENTO_FINANCIERO = ["ingreso", "gasto"]

CONDICIONES_SERVICIO_DEFAULT = (
    "Equipos Mojados: No cuentan con garantía debido a que el daño puede ser progresivo.\n"
    "Equipos Apagados: Se reciben bajo responsabilidad del cliente, ya que no se pueden "
    "verificar otras fallas hasta que enciendan; cualquier daño extra se cobrará por separado.\n"
    "Privacidad: Se garantiza la total confidencialidad de su información personal.\n"
    "Tiempo Límite: Tiene un plazo máximo de 30 días para retirar su equipo después de ser "
    "notificado, de lo contrario este pasará a ser propiedad de la empresa para cubrir costos "
    "de repuestos, mano de obra y almacenamiento."
)


def parse_condiciones_servicio(texto):
    """Convierte el texto editable de Configuración (una condición por línea,
    formato "Título: texto") en una lista de tuplas (titulo, texto) lista
    para imprimir en los PDF (orden/factura, carta y tirilla)."""
    resultado = []
    if not texto:
        return resultado
    for linea in texto.strip().split("\n"):
        linea = linea.strip()
        if not linea:
            continue
        if ":" in linea:
            titulo, resto = linea.split(":", 1)
            resultado.append((titulo.strip() + ":", resto.strip()))
        else:
            resultado.append(("", linea))
    return resultado


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    nombre_completo = Column(String(150), nullable=False)
    rol = Column(String(20), nullable=False, default="tecnico")  # admin | tecnico | vendedor
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)

    # Apariencia personal (ver "Apariencia" en el menú): cada usuario elige
    # su propio tema y mascota, guardado en su cuenta para que lo mantenga
    # sin importar desde qué computadora entre.
    tema_modo = Column(String(20), nullable=False, default="oscuro")  # claro | oscuro | vidrio
    tema_acento = Column(String(30), nullable=False, default="azul")  # azul | cian | verde | purpura | naranja | personalizado
    tema_color_personalizado = Column(String(20), nullable=True)  # ej. "#2563eb", solo si tema_acento == personalizado
    mascota = Column(String(20), nullable=False, default="panda")  # panda | leon | raton

    # Efectos de ventana (aproximaciones de macOS, ver EFECTOS_CIERRE_VENTANA):
    # cada uno se puede activar o no por separado, igual que el resto de
    # Apariencia -- son solo cosméticos, no afectan ningún dato ni cálculo.
    efecto_cierre_ventana = Column(String(20), nullable=False, default="escala")  # ninguno | genie | escala | succion
    animar_apertura_ventana = Column(Boolean, nullable=False, default=True)
    dock_magnificacion = Column(Boolean, nullable=False, default=True)
    liquid_glass = Column(Boolean, nullable=False, default=False)


class Tecnico(Base):
    __tablename__ = "tecnicos"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False)
    telefono = Column(String(30))
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)

    ordenes = relationship("OrdenServicio", back_populates="tecnico", foreign_keys="OrdenServicio.tecnico_id")


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
    condiciones_servicio = Column(Text, default=CONDICIONES_SERVICIO_DEFAULT)
    logo_data = Column(LargeBinary, nullable=True)
    logo_mime = Column(String(50), nullable=True)
    dias_vencido_alerta = Column(Integer, default=3, nullable=False)

    # --- Envío automático de WhatsApp al cliente (vía Twilio) ---
    # Si estos campos están vacíos, el sistema simplemente no manda nada
    # automático y se queda con el flujo manual (botón "Avisar por
    # WhatsApp"), sin romper nada.
    twilio_account_sid = Column(String(80), default="")
    twilio_auth_token = Column(String(120), default="")
    twilio_whatsapp_from = Column(String(40), default="")  # ej: whatsapp:+14155238886
    notificar_whatsapp_automatico = Column(Boolean, default=True, nullable=False)

    # --- Apertura y cierre de caja (ver TurnoCaja) ---
    # A partir de este momento (guardado en UTC) es obligatorio tener la caja
    # abierta para registrar cobros, abonos, facturas y ventas del POS. Si
    # está vacío, el bloqueo no aplica y el sistema funciona como antes.
    caja_obligatoria_desde = Column(DateTime, nullable=True)


# Métodos de bloqueo de un equipo (orden de servicio: Acceso al equipo).
METODOS_BLOQUEO = {
    "sin": "Sin bloqueo", "pin": "PIN", "patron": "Patrón", "contrasena": "Contraseña",
    "huella": "Huella", "rostro": "Rostro (Face ID)", "no_dio": "El cliente no la dio",
}


class OrdenServicio(Base):
    __tablename__ = "ordenes_servicio"

    id = Column(Integer, primary_key=True)
    numero_orden = Column(String(20), unique=True, nullable=False, index=True)
    fecha = Column(DateTime, default=datetime.utcnow, nullable=False)

    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    tecnico_id = Column(Integer, ForeignKey("tecnicos.id"), nullable=True)  # técnico que recibe/gestiona la orden
    # Técnico que realmente hizo la reparación (no siempre es el mismo que
    # recibió el equipo). Se puede dejar sin asignar y completar después,
    # por ejemplo al generar la factura.
    tecnico_reparacion_id = Column(Integer, ForeignKey("tecnicos.id"), nullable=True)

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
    mostrar_seguridad_en_pdf = Column(Boolean, default=False, nullable=False)
    # Métodos de bloqueo que tiene el equipo (ver METODOS_BLOQUEO), separados por coma.
    tipo_bloqueo = Column(String(80), nullable=True)
    contrasena = Column(String(100), nullable=True)        # contraseña de letras/números
    pin_sim = Column(String(20), nullable=True)
    cuenta_correo = Column(String(150), nullable=True)     # cuenta Google / iCloud del equipo
    cuenta_contrasena = Column(String(100), nullable=True)  # nunca se imprime

    # Financiero
    cotizacion = Column(Numeric(10, 2), default=0)
    recargo_pct = Column(Numeric(6, 2), default=0)
    recargo_monto = Column(Numeric(10, 2), default=0)
    repuestos_subtotal = Column(Numeric(10, 2), default=0)
    servicios_subtotal = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(10, 2), default=0)
    abonado = Column(Numeric(10, 2), default=0)
    saldo = Column(Numeric(10, 2), default=0)
    forma_pago = Column(String(20), default="Efectivo")

    fecha_entrada = Column(Date, default=date.today)
    fecha_entrega = Column(Date, nullable=True)
    fecha_cierre = Column(DateTime, nullable=True)  # se marca al llegar a ENTREGADO/CANCELADO

    # Aviso de "equipo listo": si ya se le avisó al cliente que puede pasar
    # a recogerlo. Se reinicia a False cada vez que la orden vuelve a entrar
    # a LISTO PARA ENTREGAR (por ejemplo si se corrigió algo después de
    # haber avisado), para no dejar al cliente sin el aviso correcto.
    notificado_listo = Column(Boolean, default=False, nullable=False)
    fecha_notificado_listo = Column(DateTime, nullable=True)

    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="ordenes")
    tecnico = relationship("Tecnico", back_populates="ordenes", foreign_keys=[tecnico_id])
    tecnico_reparacion = relationship("Tecnico", foreign_keys=[tecnico_reparacion_id])
    historial = relationship("HistorialEstado", back_populates="orden", cascade="all,delete-orphan", order_by="HistorialEstado.fecha")
    # Solo los abonos vigentes (los anulados con su factura no cuentan).
    pagos = relationship("Pago", back_populates="orden", cascade="all,delete-orphan", order_by="Pago.fecha",
                         primaryjoin="and_(OrdenServicio.id == Pago.orden_id, Pago.anulado == False)")
    repuestos = relationship("OrdenRepuesto", back_populates="orden", cascade="all,delete-orphan", order_by="OrdenRepuesto.fecha")
    servicios_extra = relationship("OrdenServicioExtra", back_populates="orden", cascade="all,delete-orphan", order_by="OrdenServicioExtra.fecha")
    facturas = relationship("Factura", back_populates="orden", order_by="Factura.id")

    def lista_accesorios(self):
        return [a for a in (self.accesorios or "").split(",") if a]

    def lista_condicion(self):
        return [c for c in (self.condicion_fisica or "").split(",") if c]

    def metodos_bloqueo(self) -> list:
        """Claves de METODOS_BLOQUEO marcadas. Las órdenes viejas (antes de
        este campo) se deducen de si tienen PIN o patrón."""
        metodos = [m for m in (self.tipo_bloqueo or "").split(",") if m in METODOS_BLOQUEO]
        if not metodos:
            if self.pin:
                metodos.append("pin")
            if self.patron:
                metodos.append("patron")
        return metodos

    def patron_lista(self) -> list:
        return [p for p in (self.patron or "").split(",") if p.isdigit()]

    def tiene_datos_acceso(self) -> bool:
        return bool(self.tipo_bloqueo or self.pin or self.patron or self.contrasena or self.pin_sim
                    or self.cuenta_correo or self.cuenta_contrasena)

    def acceso_partes(self) -> list:
        """Líneas de acceso para los documentos impresos (solo si el cliente
        lo autorizó con mostrar_seguridad_en_pdf). La contraseña de la
        cuenta Google/iCloud nunca se imprime."""
        partes = []
        metodos = self.metodos_bloqueo()
        if metodos:
            partes.append("Bloqueo: " + ", ".join(METODOS_BLOQUEO[m] for m in metodos))
        if self.pin:
            partes.append(f"PIN: {self.pin}")
        if self.patron:
            partes.append("Patrón: " + "-".join(self.patron_lista()))
        if self.contrasena:
            partes.append(f"Contraseña: {self.contrasena}")
        if self.pin_sim:
            partes.append(f"PIN de la SIM: {self.pin_sim}")
        if self.cuenta_correo:
            partes.append(f"Cuenta: {self.cuenta_correo}")
        return partes

    def dias_en_taller(self):
        """Días calendario (hora de Honduras, UTC-6) desde que se recibió
        el equipo. El día que llega cuenta como día 1, y el número sube
        al pasar la medianoche local (no espera 24h exactas). Se congela
        en la fecha en que la orden llegó a ENTREGADO/CANCELADO
        (fecha_cierre); si sigue activa, sigue contando hasta hoy."""
        if not self.fecha:
            return 0
        inicio = self.fecha.replace(tzinfo=timezone.utc).astimezone(HN_TZ).date()
        fin_dt = self.fecha_cierre or datetime.utcnow()
        fin = fin_dt.replace(tzinfo=timezone.utc).astimezone(HN_TZ).date()
        return max((fin - inicio).days + 1, 1)


Index("ix_ordenes_marca_modelo", OrdenServicio.marca, OrdenServicio.modelo)


class OrdenRepuesto(Base):
    """Repuesto/producto del inventario consumido en una orden de servicio.
    Cada registro descuenta existencia del producto y genera una venta
    (ver app/routers/ordenes.py) para que quede reflejado en reportes."""
    __tablename__ = "orden_repuestos"

    id = Column(Integer, primary_key=True)
    orden_id = Column(Integer, ForeignKey("ordenes_servicio.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=True)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    usuario_nombre = Column(String(150))
    # Costo del producto en el momento de usarlo (para el costo de ventas
    # de los Estados Financieros). Se llena solo, ver
    # app/utils/inventario_costos.py. Vacío en los registros anteriores.
    costo_unitario = Column(Numeric(10, 2), nullable=True)

    orden = relationship("OrdenServicio", back_populates="repuestos")
    producto = relationship("Producto")
    venta = relationship("Venta")


class Servicio(Base):
    """Catálogo de servicios que ofrece el taller (ej. 'Cambio de pantalla',
    'Formateo', 'Diagnóstico a profundidad'), cada uno con su propio precio
    de venta. El costo es OPCIONAL porque no todos los servicios lo tienen:
    algunos son 100% mano de obra (sin costo), y otros sí llevan un costo
    (por ejemplo un técnico subcontratado o un insumo que no se controla en
    Inventario). Ese costo permite calcular la utilidad del servicio en
    Reportes, igual que ya se hace con los productos del inventario."""
    __tablename__ = "servicios"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), unique=True, nullable=False, index=True)
    descripcion = Column(Text, default="")
    categoria = Column(String(80), default="")
    precio_venta = Column(Numeric(10, 2), nullable=False, default=0)
    costo = Column(Numeric(10, 2), nullable=True)  # None = sin costo (no todos los servicios lo tienen)
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)


class OrdenServicioExtra(Base):
    """Un servicio del catálogo (ver Servicio) agregado a una orden, además
    de la cotización base del equipo: por ejemplo cuando el trabajo
    combina varios servicios con nombre propio (diagnóstico + formateo), o
    se agrega un servicio adicional ya avanzada la orden. Guarda su propio
    precio y costo unitario al momento de agregarlo (puede ajustarse del
    precio de catálogo), para que un cambio posterior en el catálogo no
    altere órdenes o facturas ya emitidas."""
    __tablename__ = "orden_servicios_extra"

    id = Column(Integer, primary_key=True)
    orden_id = Column(Integer, ForeignKey("ordenes_servicio.id"), nullable=False)
    servicio_id = Column(Integer, ForeignKey("servicios.id"), nullable=False)
    cantidad = Column(Integer, nullable=False, default=1)
    precio_unitario = Column(Numeric(10, 2), nullable=False)
    costo_unitario = Column(Numeric(10, 2), nullable=True)
    subtotal = Column(Numeric(10, 2), nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    usuario_nombre = Column(String(150))

    orden = relationship("OrdenServicio", back_populates="servicios_extra")
    servicio = relationship("Servicio")


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
    # Turno de caja (apertura) en el que se recibió este abono; se llena solo
    # (ver app/utils/turnos_caja.py). Vacío en los abonos de antes del módulo.
    turno_caja_id = Column(Integer, nullable=True, index=True)
    # Anulado junto con la factura de la orden ("también anular el cobro"):
    # ya no cuenta en el abonado de la orden, la Caja, Inicio ni reportes.
    anulado = Column(Boolean, nullable=False, default=False)
    anulado_factura_id = Column(Integer, nullable=True)

    orden = relationship("OrdenServicio", back_populates="pagos")


class Categoria(Base):
    """Categorías de inventario controladas por el sistema: hay que crearlas
    aquí antes de poder asignarlas a un producto (evita duplicados como
    'PANTALLA' / 'PANTALLAS')."""
    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(80), unique=True, nullable=False)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, default=datetime.utcnow)


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
    stock_maximo = Column(Integer, nullable=True)  # para el reorden: hasta cuánto pedir
    proveedor = Column(String(150))
    caja = Column(String(40), default="")  # número/nombre de la caja o casillero donde está guardado
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
    # Desde el módulo de Ajustes de inventario (se llenan solos, ver
    # app/utils/inventario_costos.py; vacíos en los movimientos anteriores):
    existencia_anterior = Column(Integer, nullable=True)
    costo_unitario = Column(Numeric(10, 2), nullable=True)  # costo del producto en ese momento
    ajuste_id = Column(Integer, nullable=True, index=True)  # AjusteInventario que lo generó

    producto = relationship("Producto", back_populates="movimientos")


class Venta(Base):
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True)
    numero_venta = Column(String(20), unique=True, nullable=False, index=True)
    fecha = Column(DateTime, default=datetime.utcnow)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    orden_id = Column(Integer, ForeignKey("ordenes_servicio.id"), nullable=True)
    subtotal = Column(Numeric(10, 2), default=0)
    descuento = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(10, 2), default=0)
    forma_pago = Column(String(20), default="Efectivo")
    monto_recibido = Column(Numeric(10, 2), default=0)
    cambio = Column(Numeric(10, 2), default=0)
    usuario_nombre = Column(String(150))
    turno_caja_id = Column(Integer, nullable=True, index=True)  # ver TurnoCaja
    anulada = Column(Boolean, nullable=False, default=False)  # se anuló con su recibo: no cuenta

    cliente = relationship("Cliente", back_populates="ventas")
    orden = relationship("OrdenServicio")
    detalles = relationship("DetalleVenta", back_populates="venta", cascade="all,delete-orphan")


class DetalleVenta(Base):
    __tablename__ = "detalle_ventas"

    id = Column(Integer, primary_key=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    costo_unitario = Column(Numeric(10, 2), nullable=True)  # ver OrdenRepuesto.costo_unitario
    # Precio del inventario al momento de vender; si es distinto de
    # precio_unitario, la cajera cambió el precio en el Punto de Venta.
    precio_lista = Column(Numeric(10, 2), nullable=True)

    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto")


class MovimientoFinanciero(Base):
    """Ingresos y gastos generales del taller (contabilidad), y también el
    libro de donde se arma el módulo de Caja (apertura/cierre, liquidez,
    conciliación bancaria y egresos mayores) — en vez de llevar una tabla
    aparte, se reutiliza esta misma para que Contabilidad, Reportes y el
    Dashboard sigan viendo automáticamente todo lo que pasa por Caja."""
    __tablename__ = "movimientos_financieros"

    id = Column(Integer, primary_key=True)
    tipo = Column(String(10), nullable=False)  # ingreso | gasto
    categoria = Column(String(80), nullable=False)
    monto = Column(Numeric(10, 2), nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow, index=True)
    descripcion = Column(Text, default="")
    usuario_nombre = Column(String(150))
    referencia = Column(String(100), default="")  # ej: "Orden OS-000001"

    # --- Módulo de Caja ---
    # Cuenta a la que afecta el movimiento: "caja_chica" (efectivo físico) o
    # "banco" (cuenta bancaria del taller). Todo lo que ya existía antes de
    # este módulo (ventas POS, abonos, pagos automáticos, gastos manuales de
    # Contabilidad) queda en "caja_chica" por ser el comportamiento histórico
    # del sistema; lo nuevo que SÍ sabe distinguir cuenta real es lo que pasa
    # por Caja: el cobro con Tarjeta (POS) o Transferencia se contabiliza en
    # "banco", y los Egresos Mayores del Administrador siempre son "banco".
    cuenta = Column(String(20), nullable=False, default="caja_chica")
    # Método de cobro/pago: en un ingreso creado desde "Registrar cobro"
    # (Vista Cajera) es Efectivo/Transferencia/Tarjeta (POS); en un egreso
    # manual creado desde Reportes > Egresos es de dónde salió el dinero
    # (ver FORMAS_PAGO). Las demás rutas del sistema lo dejan vacío.
    metodo_pago = Column(String(30), nullable=True)
    cliente_nombre = Column(String(150), nullable=True)
    num_referencia = Column(String(60), nullable=True)  # N. de comprobante de la transferencia
    comprobante_data = Column(LargeBinary, nullable=True)
    comprobante_mime = Column(String(50), nullable=True)
    # Conciliación bancaria de las transferencias registradas por la Cajera.
    estado_conciliacion = Column(String(20), nullable=True)  # pendiente | conciliado
    conciliado_por = Column(String(150), nullable=True)
    conciliado_en = Column(DateTime, nullable=True)

    # Vincula las dos filas de un Depósito bancario (remesa): la salida de
    # Caja Chica y su contraparte, la entrada a Banco. Se usa para que editar
    # o eliminar una de las dos arrastre a la otra y nunca queden
    # descuadradas o huérfanas (ver CATEGORIA_DEPOSITO_BANCO).
    movimiento_vinculado_id = Column(Integer, ForeignKey("movimientos_financieros.id"), nullable=True)

    # Si esta fila ya NO debe sumar en Ingresos/Caja/Utilidad Neta/
    # Contabilidad, pero se conserva en la base de datos sin borrarse (ver
    # CATEGORIAS_ORDEN_EXCLUIDAS_CONTABILIDAD). Se usa en vez de eliminar
    # filas para no perder nunca el historial real de lo que pasó.
    excluir_de_contabilidad = Column(Boolean, nullable=False, default=False)

    # Si este ingreso viene de una Factura (ver CATEGORIA_VENTA_FACTURADA):
    # permite, por ejemplo, excluirlo también si esa factura se anula.
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=True)

    # Turno de caja (apertura) en el que se registró; se llena solo (ver
    # app/utils/turnos_caja.py). Vacío en los movimientos de antes del módulo.
    turno_caja_id = Column(Integer, nullable=True, index=True)

    # Pago de una Recepción de compra (ver RecepcionCompra): así las Compras
    # de los Estados Financieros no la cuentan dos veces.
    recepcion_compra_id = Column(Integer, nullable=True, index=True)


class SaldoInicialMensual(Base):
    """Saldo con el que arranca cada mes la Caja Chica y la cuenta de Banco,
    que el Administrador registra/ajusta al 1 de cada mes (Configuración de
    Saldos). A partir de este saldo se calcula la Liquidez Total, sumando
    los ingresos y restando los egresos del mes en curso."""
    __tablename__ = "saldos_iniciales_mensuales"
    __table_args__ = (UniqueConstraint("anio", "mes", name="uq_saldo_inicial_anio_mes"),)

    id = Column(Integer, primary_key=True)
    anio = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=False)  # 1-12
    saldo_inicial_caja_chica = Column(Numeric(10, 2), nullable=False, default=0)
    saldo_inicial_banco = Column(Numeric(10, 2), nullable=False, default=0)
    usuario_nombre = Column(String(150))
    actualizado_en = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Libro Diario (contabilidad de partida doble). Corre en PARALELO al libro de
# caja de una sola entrada (MovimientoFinanciero) que ya existía: no lo
# reemplaza ni lo modifica. Cada vez que se crea un MovimientoFinanciero
# relevante (un cobro, una venta, un gasto, etc.) se genera automáticamente
# su asiento correspondiente aquí, con las cuentas de Debe/Haber que le
# tocan según el tipo de evento (ver app/utils/libro_diario.py para el
# catálogo de cuentas y las reglas de asiento por evento).
# ---------------------------------------------------------------------------
class CuentaContable(Base):
    __tablename__ = "cuentas_contables"

    id = Column(Integer, primary_key=True)
    codigo = Column(String(20), unique=True, nullable=False)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(20), nullable=False)  # activo | pasivo | capital | ingreso | gasto
    naturaleza = Column(String(10), nullable=False)  # deudora | acreedora
    activa = Column(Boolean, default=True, nullable=False)


class AsientoContable(Base):
    """Un asiento del Libro Diario: siempre debe quedar balanceado (la suma
    de Debe == la suma de Haber entre sus detalles) — registrar_asiento() en
    app/utils/libro_diario.py lo garantiza antes de guardarlo. Se crea
    automáticamente al registrar un MovimientoFinanciero relevante; el
    campo movimiento_financiero_id enlaza con ese movimiento de Caja para
    poder encontrar/corregir su asiento si el movimiento se edita o
    elimina (ver caja_movimiento_editar/eliminar en app/routers/caja.py)."""
    __tablename__ = "asientos_contables"

    id = Column(Integer, primary_key=True)
    numero_asiento = Column(String(20), unique=True, nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow, index=True)
    concepto = Column(String(255), nullable=False)
    tipo_evento = Column(String(40), nullable=False)
    referencia = Column(String(100), default="")
    movimiento_financiero_id = Column(Integer, ForeignKey("movimientos_financieros.id"), nullable=True)
    usuario_nombre = Column(String(150))

    detalles = relationship(
        "DetalleAsiento", backref="asiento",
        cascade="all, delete-orphan", order_by="DetalleAsiento.id",
    )


class DetalleAsiento(Base):
    __tablename__ = "detalles_asiento"

    id = Column(Integer, primary_key=True)
    asiento_id = Column(Integer, ForeignKey("asientos_contables.id"), nullable=False)
    cuenta_id = Column(Integer, ForeignKey("cuentas_contables.id"), nullable=False)
    debe = Column(Numeric(10, 2), nullable=False, default=0)
    haber = Column(Numeric(10, 2), nullable=False, default=0)

    cuenta = relationship("CuentaContable")


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
    # Cuando queden estas facturas o menos dentro del rango autorizado, el
    # sistema muestra un aviso en todas las pantallas (no solo al agotarse).
    alerta_umbral_fiscal = Column(Integer, default=50)

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
    turno_caja_id = Column(Integer, nullable=True, index=True)  # ver TurnoCaja

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


# ---------------------------------------------------------------------------
# Apertura y cierre de caja (turnos). Cada apertura agrupa, desde ese momento
# hasta su cierre, todo lo que mueve dinero: abonos de órdenes, cobros de
# Caja, ventas del POS, facturas y salidas de caja (ver la columna
# turno_caja_id en Pago, MovimientoFinanciero, Venta y Factura, que se llena
# sola en app/utils/turnos_caja.py). NO reemplaza ni modifica el registro
# contable: Liquidez, Contabilidad y Reportes siguen calculándose igual que
# antes; esto es una capa encima para controlar el efectivo de cada turno.
# ---------------------------------------------------------------------------
TURNO_ABIERTO = "abierta"
TURNO_CERRADO = "cerrada"


class TurnoCaja(Base):
    __tablename__ = "turnos_caja"

    id = Column(Integer, primary_key=True)
    estado = Column(String(10), nullable=False, default=TURNO_ABIERTO, index=True)

    fecha_apertura = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    abierta_por = Column(String(150), default="")
    monto_inicial = Column(Numeric(10, 2), nullable=False, default=0)  # efectivo contado al abrir
    notas_apertura = Column(Text, default="")

    fecha_cierre = Column(DateTime, nullable=True)
    cerrada_por = Column(String(150), nullable=True)
    # Arqueo: lo que el sistema calcula que debería haber en efectivo, lo
    # que la cajera contó, y la diferencia (contado - esperado: positiva es
    # sobrante, negativa es faltante). Se guardan al cerrar.
    efectivo_esperado = Column(Numeric(10, 2), nullable=True)
    efectivo_contado = Column(Numeric(10, 2), nullable=True)
    diferencia = Column(Numeric(10, 2), nullable=True)
    notas_cierre = Column(Text, default="")
    # Se cerró otro día después del que se abrió (se olvidó cerrar).
    cerrada_tarde = Column(Boolean, nullable=False, default=False)

    eventos = relationship(
        "TurnoCajaEvento", back_populates="turno", cascade="all,delete-orphan",
        order_by="TurnoCajaEvento.fecha",
    )


class TurnoCajaEvento(Base):
    """Bitácora de cada turno: apertura, cierre, reapertura y ediciones
    (quién, cuándo y qué cambió)."""
    __tablename__ = "turnos_caja_eventos"

    id = Column(Integer, primary_key=True)
    turno_id = Column(Integer, ForeignKey("turnos_caja.id"), nullable=False, index=True)
    fecha = Column(DateTime, nullable=False, default=datetime.utcnow)
    accion = Column(String(20), nullable=False)  # apertura | cierre | reapertura | edicion
    usuario_nombre = Column(String(150), default="")
    detalle = Column(Text, default="")

    turno = relationship("TurnoCaja", back_populates="eventos")


# ---------------------------------------------------------------------------
# Ajustes de inventario: un ajuste es un documento (AJ-000001) que cambia la
# existencia de uno o varios productos a la vez, con un motivo. Cada línea
# genera su MovimientoInventario (tipo "ajuste", con ajuste_id) y queda
# valorada al costo del producto en ese momento, para los reportes en
# lempiras y el Estado de Resultados (pérdida o sobrante por ajuste). No
# genera movimientos de dinero: un ajuste no es entrada ni salida de caja.
# ---------------------------------------------------------------------------
MOTIVOS_AJUSTE_INVENTARIO = [
    "Conteo físico", "Merma / daño", "Robo o pérdida", "Error de registro",
    "Devolución de cliente", "Devolución a proveedor", "Uso interno / garantía", "Otro",
]
MOTIVO_REVERSION_AJUSTE = "Reversión de ajuste"


class AjusteInventario(Base):
    __tablename__ = "ajustes_inventario"

    id = Column(Integer, primary_key=True)
    numero = Column(String(20), unique=True, nullable=False, index=True)
    fecha = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    usuario_nombre = Column(String(150), default="")
    motivo = Column(String(60), nullable=False)
    observacion = Column(Text, default="")
    origen = Column(String(12), nullable=False, default="manual")  # manual | excel | reversion

    unidades_entrada = Column(Integer, nullable=False, default=0)   # suma de lo que subió
    unidades_salida = Column(Integer, nullable=False, default=0)    # suma de lo que bajó
    valor_entrada = Column(Numeric(12, 2), nullable=False, default=0)
    valor_salida = Column(Numeric(12, 2), nullable=False, default=0)

    revierte_a_id = Column(Integer, nullable=True)     # si este ajuste deshace otro
    revertido_por_id = Column(Integer, nullable=True)  # si otro ajuste deshizo este

    detalles = relationship(
        "AjusteInventarioDetalle", back_populates="ajuste", cascade="all,delete-orphan",
        order_by="AjusteInventarioDetalle.id",
    )

    @property
    def valor_neto(self):
        return (self.valor_entrada or 0) - (self.valor_salida or 0)


class AjusteInventarioDetalle(Base):
    __tablename__ = "ajustes_inventario_detalle"

    id = Column(Integer, primary_key=True)
    ajuste_id = Column(Integer, ForeignKey("ajustes_inventario.id"), nullable=False, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    producto_codigo = Column(String(50), default="")   # copia al momento del ajuste
    producto_nombre = Column(String(150), default="")
    existencia_anterior = Column(Integer, nullable=False)
    existencia_nueva = Column(Integer, nullable=False)
    diferencia = Column(Integer, nullable=False)        # positiva sube, negativa baja
    costo_unitario = Column(Numeric(10, 2), nullable=False, default=0)
    valor = Column(Numeric(12, 2), nullable=False, default=0)  # diferencia x costo (con signo)

    ajuste = relationship("AjusteInventario", back_populates="detalles")
    producto = relationship("Producto")


# ---------------------------------------------------------------------------
# Datos del Balance General que el sistema no registra por sí solo: activos
# fijos (equipo, herramientas, mobiliario...), otros activos, deudas con
# proveedores, préstamos, aportes de capital y retiros del dueño. Solo los
# registra el administrador (ver app/routers/estados_financieros.py). Son
# registros informativos para los Estados Financieros: NO mueven Caja ni
# Banco ni cambian ningún otro dato del sistema.
# ---------------------------------------------------------------------------
TIPOS_PARTIDA_BALANCE = {
    "activo_fijo": "Activo fijo (equipo, herramientas, mobiliario, vehículo)",
    "otro_activo": "Otro activo (cuentas por cobrar, depósitos en garantía...)",
    "cuenta_por_pagar": "Cuenta por pagar (proveedores)",
    "prestamo": "Préstamo",
    "otro_pasivo": "Otro pasivo",
    "capital": "Aporte de capital del dueño",
    "retiro": "Retiro del dueño",
}


class PartidaBalance(Base):
    __tablename__ = "partidas_balance"

    id = Column(Integer, primary_key=True)
    tipo = Column(String(20), nullable=False, index=True)  # ver TIPOS_PARTIDA_BALANCE
    descripcion = Column(String(200), nullable=False)
    monto = Column(Numeric(12, 2), nullable=False, default=0)
    fecha = Column(Date, nullable=False)                  # desde cuándo cuenta
    fecha_baja = Column(Date, nullable=True)              # desde cuándo ya no (vendido, pagado...)
    vida_util_meses = Column(Integer, nullable=False, default=0)  # solo activos fijos; 0 = no se deprecia
    notas = Column(Text, default="")
    usuario_nombre = Column(String(150), default="")
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow)

    def vigente_en(self, dia) -> bool:
        return self.fecha <= dia and (self.fecha_baja is None or self.fecha_baja > dia)


# ---------------------------------------------------------------------------
# Compras: solicitud de compra -> recepción (confirmación) -> pago.
# Las unidades de un producto SOLO entran al inventario con una recepción
# (ver app/utils/compras.py). Solo el administrador usa este módulo.
# ---------------------------------------------------------------------------
COMPRA_PENDIENTE = "pendiente"        # solicitada, nada recibido
COMPRA_PARCIAL = "parcial"            # recibida en parte
COMPRA_RECIBIDA = "recibida"          # todo recibido
COMPRA_CERRADA = "cerrada"            # se cerró sin recibir todo
COMPRA_ANULADA = "anulada"            # se anuló antes de recibir nada
ESTADOS_COMPRA = {
    COMPRA_PENDIENTE: "Pendiente de recibir", COMPRA_PARCIAL: "Recibida en parte",
    COMPRA_RECIBIDA: "Recibida", COMPRA_CERRADA: "Cerrada (no llegó todo)", COMPRA_ANULADA: "Anulada",
}
PAGO_COMPRA_EFECTIVO = "Efectivo"     # sale de la caja abierta (Caja Chica)
PAGO_COMPRA_BANCO = "Banco"           # transferencia (Banco)
PAGO_COMPRA_CREDITO = "Crédito"       # queda por pagar al proveedor
FORMAS_PAGO_COMPRA = (PAGO_COMPRA_EFECTIVO, PAGO_COMPRA_BANCO, PAGO_COMPRA_CREDITO)
CATEGORIA_COMPRA_MERCADERIA = "Compras"


class SolicitudCompra(Base):
    __tablename__ = "solicitudes_compra"

    id = Column(Integer, primary_key=True)
    numero = Column(String(20), unique=True, nullable=False, index=True)  # SC-000001
    fecha = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    proveedor = Column(String(150), nullable=False, default="")
    proveedor_id = Column(Integer, nullable=True)  # ver Proveedor (si se eligió de la lista)
    notas = Column(Text, default="")
    estado = Column(String(12), nullable=False, default=COMPRA_PENDIENTE, index=True)
    total_estimado = Column(Numeric(12, 2), nullable=False, default=0)
    usuario_nombre = Column(String(150), default="")
    cerrada_en = Column(DateTime, nullable=True)
    cerrada_por = Column(String(150), nullable=True)
    motivo_cierre = Column(Text, nullable=True)

    detalles = relationship("SolicitudCompraDetalle", back_populates="solicitud", cascade="all,delete-orphan",
                            order_by="SolicitudCompraDetalle.id")
    recepciones = relationship("RecepcionCompra", back_populates="solicitud", order_by="RecepcionCompra.id")


class SolicitudCompraDetalle(Base):
    __tablename__ = "solicitudes_compra_detalle"

    id = Column(Integer, primary_key=True)
    solicitud_id = Column(Integer, ForeignKey("solicitudes_compra.id"), nullable=False, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    cantidad = Column(Integer, nullable=False)
    cantidad_recibida = Column(Integer, nullable=False, default=0)
    costo_unitario = Column(Numeric(10, 2), nullable=False, default=0)  # costo esperado (sin ISV)
    precio_venta = Column(Numeric(10, 2), nullable=True)  # nuevo precio de venta (sin ISV); se aplica al recibir

    solicitud = relationship("SolicitudCompra", back_populates="detalles")
    producto = relationship("Producto")

    @property
    def pendiente(self) -> int:
        return max(0, (self.cantidad or 0) - (self.cantidad_recibida or 0))


class RecepcionCompra(Base):
    __tablename__ = "recepciones_compra"

    id = Column(Integer, primary_key=True)
    numero = Column(String(20), unique=True, nullable=False, index=True)  # RC-000001
    solicitud_id = Column(Integer, ForeignKey("solicitudes_compra.id"), nullable=False, index=True)
    fecha = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    proveedor = Column(String(150), default="")
    factura_proveedor = Column(String(60), default="")
    forma_pago = Column(String(12), nullable=False)          # ver FORMAS_PAGO_COMPRA
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)  # costo de la mercadería (sin ISV)
    isv = Column(Numeric(12, 2), nullable=False, default=0)       # ISV de la factura del proveedor (crédito fiscal)
    total = Column(Numeric(12, 2), nullable=False, default=0)     # subtotal + isv: lo que se paga
    pagado = Column(Numeric(12, 2), nullable=False, default=0)
    notas = Column(Text, default="")
    usuario_nombre = Column(String(150), default="")
    anulada = Column(Boolean, nullable=False, default=False)   # se anuló la compra: no cuenta en nada
    anulada_en = Column(DateTime, nullable=True)
    anulada_por = Column(String(150), nullable=True)
    motivo_anulacion = Column(Text, nullable=True)

    solicitud = relationship("SolicitudCompra", back_populates="recepciones")
    detalles = relationship("RecepcionCompraDetalle", back_populates="recepcion", cascade="all,delete-orphan",
                            order_by="RecepcionCompraDetalle.id")

    @property
    def saldo(self):
        if self.anulada:
            return 0
        return (self.total or 0) - (self.pagado or 0)


class RecepcionCompraDetalle(Base):
    __tablename__ = "recepciones_compra_detalle"

    id = Column(Integer, primary_key=True)
    recepcion_id = Column(Integer, ForeignKey("recepciones_compra.id"), nullable=False, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    cantidad = Column(Integer, nullable=False)
    costo_unitario = Column(Numeric(10, 2), nullable=False, default=0)   # costo real de la factura (sin ISV)
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    existencia_anterior = Column(Integer, nullable=False, default=0)
    costo_anterior = Column(Numeric(10, 2), nullable=False, default=0)
    costo_nuevo = Column(Numeric(10, 2), nullable=False, default=0)       # costo promedio que quedó
    precio_anterior = Column(Numeric(10, 2), nullable=True)               # precio de venta antes de recibir
    precio_nuevo = Column(Numeric(10, 2), nullable=True)                  # precio de venta que quedó

    recepcion = relationship("RecepcionCompra", back_populates="detalles")
    producto = relationship("Producto")


class HistorialProducto(Base):
    """Cada cambio de datos de un producto (nombre, categoría, costo,
    precio...) hecho a mano en Inventario: quién, cuándo, antes y después."""
    __tablename__ = "historial_productos"

    id = Column(Integer, primary_key=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    fecha = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    usuario_nombre = Column(String(150), default="")
    campo = Column(String(40), nullable=False)
    antes = Column(String(200), default="")
    despues = Column(String(200), default="")
    origen = Column(String(30), default="")  # editar | editar_varios



# ---------------------------------------------------------------------------
# Mejoras tomadas de Zafra (migración 0033)
# ---------------------------------------------------------------------------
class Proveedor(Base):
    __tablename__ = "proveedores"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False, index=True)
    rtn = Column(String(20), default="")
    telefono = Column(String(30), default="")
    whatsapp = Column(String(30), default="")
    correo = Column(String(150), default="")
    direccion = Column(String(255), default="")
    contacto = Column(String(150), default="")
    notas = Column(Text, default="")
    activo = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime, default=datetime.utcnow)


COTIZACION_VIGENTE = "vigente"
COTIZACION_ACEPTADA = "aceptada"
COTIZACION_ANULADA = "anulada"
ESTADOS_COTIZACION = {COTIZACION_VIGENTE: "Vigente", COTIZACION_ACEPTADA: "Vendida", COTIZACION_ANULADA: "Anulada", "vencida": "Vencida"}


class Cotizacion(Base):
    __tablename__ = "cotizaciones"

    id = Column(Integer, primary_key=True)
    numero = Column(String(20), unique=True, nullable=False)  # COT-000001
    fecha = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    cliente_nombre = Column(String(150), default="")
    cliente_telefono = Column(String(30), default="")
    validez_dias = Column(Integer, nullable=False, default=15)
    notas = Column(Text, default="")
    estado = Column(String(12), nullable=False, default=COTIZACION_VIGENTE)
    precios_con_isv = Column(Boolean, nullable=False, default=True)
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)   # sin ISV
    isv = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)      # lo que paga el cliente
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=True)
    usuario_nombre = Column(String(150), default="")

    cliente = relationship("Cliente")
    detalles = relationship("CotizacionDetalle", back_populates="cotizacion", cascade="all,delete-orphan",
                            order_by="CotizacionDetalle.id")

    @property
    def vence(self):
        from datetime import timedelta
        return (self.fecha or datetime.utcnow()) + timedelta(days=self.validez_dias or 0)

    @property
    def estado_actual(self):
        if self.estado == COTIZACION_VIGENTE and datetime.utcnow() > self.vence:
            return "vencida"
        return self.estado


class CotizacionDetalle(Base):
    __tablename__ = "cotizaciones_detalle"

    id = Column(Integer, primary_key=True)
    cotizacion_id = Column(Integer, ForeignKey("cotizaciones.id"), nullable=False, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=True)
    descripcion = Column(String(200), nullable=False)
    cantidad = Column(Integer, nullable=False, default=1)
    precio_unitario = Column(Numeric(10, 2), nullable=False, default=0)  # sin ISV
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)

    cotizacion = relationship("Cotizacion", back_populates="detalles")
    producto = relationship("Producto")


class Bitacora(Base):
    """Quién hizo qué y cuándo (cada acción que guarda algo en el sistema)."""
    __tablename__ = "bitacora"

    id = Column(Integer, primary_key=True)
    fecha = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    usuario_nombre = Column(String(150), default="")
    usuario_rol = Column(String(20), default="")
    modulo = Column(String(40), default="")
    accion = Column(String(200), nullable=False)
    ruta = Column(String(255), default="")
    enlace = Column(String(255), default="")
    resultado = Column(String(10), default="")
    ip = Column(String(60), default="")
