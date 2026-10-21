"""Bitácora: quién hizo qué y cuándo.

Un middleware anota cada acción que guarda algo (todo POST que no termina
en error), con el usuario, la hora, el módulo y una descripción en
palabras simples sacada de la ruta. No lee los formularios (así nunca
guarda contraseñas ni datos sensibles)."""
import re
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware

# (patrón de la ruta, módulo, descripción, enlace) — {1}, {2} = números de la ruta
RUTAS = [
    (r"^/login$", "Acceso", "Inició sesión", ""),
    (r"^/ordenes/nueva$", "Órdenes", "Creó una orden", ""),
    (r"^/ordenes/(\d+)/editar$", "Órdenes", "Editó la orden #{1}", "/ordenes/{1}"),
    (r"^/ordenes/(\d+)/estado$", "Órdenes", "Cambió el estado de la orden #{1}", "/ordenes/{1}"),
    (r"^/ordenes/(\d+)/abono$", "Órdenes", "Registró un abono en la orden #{1}", "/ordenes/{1}"),
    (r"^/ordenes/(\d+)/factura/nueva$", "Facturas", "Generó la factura de la orden #{1}", "/ordenes/{1}"),
    (r"^/ordenes/(\d+)/repuestos$", "Órdenes", "Agregó un repuesto a la orden #{1}", "/ordenes/{1}"),
    (r"^/ordenes/(\d+)/repuestos/\d+/eliminar$", "Órdenes", "Quitó un repuesto de la orden #{1}", "/ordenes/{1}"),
    (r"^/ordenes/(\d+)/servicios$", "Órdenes", "Agregó un servicio a la orden #{1}", "/ordenes/{1}"),
    (r"^/ordenes/(\d+)/servicios/\d+/eliminar$", "Órdenes", "Quitó un servicio de la orden #{1}", "/ordenes/{1}"),
    (r"^/ordenes/(\d+)/revertir-cancelacion$", "Órdenes", "Revirtió la cancelación de la orden #{1}", "/ordenes/{1}"),
    (r"^/ordenes/(\d+)/marcar-avisado$", "Órdenes", "Marcó como avisado al cliente de la orden #{1}", "/ordenes/{1}"),
    (r"^/facturas/(\d+)/anular$", "Facturas", "ANULÓ la factura #{1}", "/facturas/{1}"),
    (r"^/ordenes/(\d+)/abonos/(\d+)/anular$", "Órdenes", "ANULÓ un abono de la orden #{1}", "/ordenes/{1}"),
    (r"^/facturas/(\d+)/anular-cobro$", "Facturas", "ANULÓ el cobro de la factura #{1}", "/facturas/{1}"),
    (r"^/facturas/(\d+)/desanular$", "Facturas", "DESANULÓ (volvió a activar) la factura #{1}", "/facturas/{1}"),
    (r"^/pos/vender$", "Punto de venta", "Hizo una venta en el Punto de Venta", ""),
    (r"^/clientes/nuevo$|^/clientes/rapido$", "Clientes", "Creó un cliente", ""),
    (r"^/clientes/(\d+)/editar$", "Clientes", "Editó el cliente #{1}", "/clientes/{1}"),
    (r"^/clientes/(\d+)/eliminar$", "Clientes", "ELIMINÓ el cliente #{1}", ""),
    (r"^/inventario/nuevo$", "Inventario", "Creó un producto", ""),
    (r"^/inventario/(\d+)/editar$", "Inventario", "Editó el producto #{1}", "/inventario/{1}/movimiento"),
    (r"^/inventario/(\d+)/eliminar$", "Inventario", "ELIMINÓ el producto #{1}", ""),
    (r"^/inventario/(\d+)/movimiento$", "Inventario", "Movió existencias del producto #{1}", "/inventario/{1}/movimiento"),
    (r"^/inventario/ajustes/(\d+)$", "Inventario", "Ajuste rápido de existencias del producto #{1}", "/inventario/{1}/movimiento"),
    (r"^/inventario/editar-varios$", "Inventario", "Editó varios productos a la vez", "/inventario/editar-varios"),
    (r"^/inventario/importar/confirmar$", "Inventario", "Importó productos desde Excel", ""),
    (r"^/inventario/categorias", "Inventario", "Cambió las categorías", "/inventario/categorias"),
    (r"^/inventario/reorden/solicitud$", "Compras", "Creó una solicitud de compra desde el reorden", ""),
    (r"^/ajustes-inventario/nuevo$", "Inventario", "Hizo un ajuste de inventario", "/ajustes-inventario"),
    (r"^/ajustes-inventario/importar/confirmar$", "Inventario", "Hizo un ajuste de inventario desde Excel", "/ajustes-inventario"),
    (r"^/ajustes-inventario/(\d+)/revertir$", "Inventario", "REVIRTIÓ el ajuste de inventario #{1}", "/ajustes-inventario/{1}"),
    (r"^/compras/nueva$", "Compras", "Creó una solicitud de compra", ""),
    (r"^/compras/producto-rapido$", "Compras", "Creó un producto desde Compras", ""),
    (r"^/compras/(\d+)/recibir$", "Compras", "Confirmó la recepción de la compra #{1}", "/compras/{1}"),
    (r"^/compras/(\d+)/anular$", "Compras", "ANULÓ la solicitud de compra #{1}", "/compras/{1}"),
    (r"^/compras/(\d+)/cerrar$", "Compras", "Cerró la solicitud de compra #{1}", "/compras/{1}"),
    (r"^/compras/recepcion/(\d+)/pagar$", "Compras", "Pagó al proveedor la recepción #{1}", ""),
    (r"^/compras/recepcion/(\d+)/agregar-isv$", "Compras", "Agregó el ISV a la recepción #{1} (corrección)", ""),
    (r"^/proveedores/nuevo$", "Compras", "Creó un proveedor", "/proveedores"),
    (r"^/proveedores/(\d+)/editar$", "Compras", "Editó el proveedor #{1}", "/proveedores/{1}"),
    (r"^/cotizaciones/nueva$", "Cotizaciones", "Creó una cotización", ""),
    (r"^/cotizaciones/(\d+)/anular$", "Cotizaciones", "Anuló la cotización #{1}", "/cotizaciones/{1}"),
    (r"^/caja/turnos/abrir$", "Caja", "Abrió la caja", "/caja/turnos"),
    (r"^/caja/turnos/(\d+)/cerrar$", "Caja", "Cerró la caja #{1}", "/caja/turnos/{1}"),
    (r"^/caja/turnos/(\d+)/editar$", "Caja", "CORRIGIÓ la caja #{1}", "/caja/turnos/{1}"),
    (r"^/caja/turnos/(\d+)/reabrir$", "Caja", "REABRIÓ la caja #{1}", "/caja/turnos/{1}"),
    (r"^/caja/registrar$", "Caja", "Registró un cobro en Caja", "/caja/registrar"),
    (r"^/caja/ingreso-otro$", "Caja", "Registró otro ingreso en Caja", "/caja/registrar"),
    (r"^/caja/salida$", "Caja", "Registró una salida de Caja (o depósito)", "/caja/registrar"),
    (r"^/caja/movimiento/(\d+)/editar$", "Caja", "EDITÓ el movimiento de caja #{1}", ""),
    (r"^/caja/movimiento/(\d+)/eliminar$", "Caja", "ELIMINÓ el movimiento de caja #{1}", ""),
    (r"^/caja/egresos/nuevo$", "Banco", "Registró un egreso mayor (banco)", "/caja/conciliacion"),
    (r"^/caja/conciliacion/deposito$", "Banco", "Registró un depósito bancario", "/caja/conciliacion"),
    (r"^/caja/conciliacion/(\d+)/validar$", "Banco", "Concilió la transferencia #{1}", "/caja/conciliacion"),
    (r"^/caja/panel/saldos$|^/caja/registrar/saldo-inicial$", "Caja", "CAMBIÓ el saldo inicial del mes", "/caja/panel"),
    (r"^/banco/cuadre$", "Banco", "Cuadró el banco con el saldo real", "/banco/cuadre"),
    (r"^/banco/cuadre/(\d+)/deshacer$", "Banco", "Anuló un cuadre de banco", "/banco/cuadre"),
    (r"^/revision/", "Revisión", "Hizo una corrección en Revisión del sistema", "/revision"),
    (r"^/estados-financieros/", "Contabilidad", "Cambió datos del balance", "/estados-financieros"),
    (r"^/usuarios/nuevo$", "Usuarios", "Creó un usuario", ""),
    (r"^/usuarios/(\d+)/editar$", "Usuarios", "Editó el usuario #{1}", ""),
    (r"^/usuarios/(\d+)/eliminar$", "Usuarios", "ELIMINÓ el usuario #{1}", ""),
    (r"^/usuarios/(\d+)/toggle$", "Usuarios", "Activó/desactivó el usuario #{1}", ""),
    (r"^/configuracion", "Configuración", "Cambió la configuración", "/configuracion"),
    (r"^/servicios", "Servicios", "Cambió el catálogo de servicios", "/servicios"),
    (r"^/tecnicos", "Técnicos", "Cambió los técnicos", "/tecnicos"),
    (r"^/catalogo", "Configuración", "Cambió marcas/modelos", ""),
    (r"^/reportes/movimiento", "Reportes", "Registró/corrigió un movimiento en Reportes", ""),
    (r"^/contabilidad/nuevo$", "Contabilidad", "Registró un movimiento en Contabilidad", ""),
    (r"^/admin/limpiar-datos-prueba$", "Configuración", "BORRÓ los datos de prueba", ""),
]
IGNORAR = (r"^/mi-perfil/", r"^/api/", r"^/static/", r"^/logout")
_COMPILADAS = [(re.compile(p), m, d, e) for p, m, d, e in RUTAS]
_IGNORAR = [re.compile(p) for p in IGNORAR]


def describir(ruta: str):
    for patron, modulo, texto, enlace in _COMPILADAS:
        m = patron.search(ruta)
        if m:
            grupos = m.groups()
            for i, g in enumerate(grupos, start=1):
                texto = texto.replace("{%d}" % i, g or "")
                enlace = enlace.replace("{%d}" % i, g or "")
            return modulo, texto, enlace
    segmento = ruta.strip("/").split("/")[0] or "inicio"
    return segmento.capitalize(), f"Acción en {ruta}", ""


def registrar(usuario: dict | None, ruta: str, status: int, ip: str = "") -> None:
    """Nunca lanza error: la bitácora no debe poder tumbar nada."""
    from app.database import SessionLocal
    from app.models import Bitacora
    try:
        modulo, accion, enlace = describir(ruta)
        db = SessionLocal()
        try:
            db.add(Bitacora(fecha=datetime.utcnow(), usuario_nombre=(usuario or {}).get("nombre_completo", "") if usuario else "",
                            usuario_rol=(usuario or {}).get("rol", "") if usuario else "", modulo=modulo[:40], accion=accion[:200],
                            ruta=ruta[:255], enlace=enlace[:255], resultado="ok" if status < 400 else "error", ip=(ip or "")[:60]))
            db.commit()
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        pass


class BitacoraMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.method in ("POST", "PUT", "DELETE"):
            ruta = request.url.path
            if not any(p.search(ruta) for p in _IGNORAR):
                usuario = None
                try:
                    usuario = request.session.get("usuario")
                except Exception:  # noqa: BLE001
                    usuario = None
                # Si la acción terminó con un mensaje de error (no se guardó
                # nada), no se anota en la bitácora.
                try:
                    flashes = request.session.get("_flashes") or []
                except Exception:  # noqa: BLE001
                    flashes = []
                fallo = bool(flashes) and flashes[-1].get("categoria") == "error"
                if usuario and response.status_code < 400 and not fallo:
                    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
                    registrar(usuario, ruta, response.status_code, ip)
        return response
