"""Instancia compartida de Jinja2Templates con filtros y funciones globales."""
import json
from datetime import datetime
import os
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from app.utils.flash import obtener_flashes

templates = Jinja2Templates(directory="app/templates")

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def version_estatico(ruta_relativa):
    """Devuelve la fecha de modificación de un archivo estático (CSS/JS)
    como número. Se usa como '?v=' en las etiquetas <link>/<script> para
    que el navegador descargue la versión nueva en cuanto el archivo
    cambia, en vez de quedarse con una copia vieja guardada en caché."""
    ruta_completa = os.path.join(_STATIC_DIR, ruta_relativa)
    try:
        return int(os.path.getmtime(ruta_completa))
    except OSError:
        return 0


def fmt_moneda(valor, simbolo="L"):
    try:
        return f"{simbolo} {float(valor):,.2f}"
    except (TypeError, ValueError):
        return f"{simbolo} 0.00"


def fmt_fecha(valor, formato="%d/%m/%Y"):
    if not valor:
        return ""
    # Las fechas con hora se guardan en UTC: se muestran en hora de Honduras
    # (antes salían 6 horas adelantadas). Una fecha sin hora (date) queda igual.
    if isinstance(valor, datetime) and valor.tzinfo is None:
        from app.utils.turnos_caja import a_hora_local
        valor = a_hora_local(valor)
    try:
        return valor.strftime(formato)
    except AttributeError:
        return str(valor)


def obtener_config_actual():
    """Devuelve un dict con los datos básicos del taller para usarlos en la
    barra superior / branding de todas las plantillas, sin tener que pasarlos
    manualmente en cada ruta."""
    from app.database import SessionLocal
    from app.models import Configuracion
    db = SessionLocal()
    try:
        cfg = db.get(Configuracion, 1)
        if cfg:
            logo_url = "/configuracion/logo" if cfg.logo_data else None
            return {
                "nombre_taller": cfg.nombre_taller, "moneda": cfg.moneda, "logo_path": cfg.logo_path,
                "logo_url": logo_url, "dias_vencido_alerta": cfg.dias_vencido_alerta or 3,
            }
    finally:
        db.close()
    return {"nombre_taller": "Mi Taller", "moneda": "L", "logo_path": None, "logo_url": None, "dias_vencido_alerta": 3}


def obtener_notificaciones():
    """Cuenta rápida para la campana de la barra superior: equipos listos
    para entregar que el cliente aún no ha recogido, más el aviso de rango
    de facturación fiscal por agotarse (si aplica)."""
    from app.database import SessionLocal
    from app.models import OrdenServicio, ConfiguracionFacturacion
    from app.utils.numbering import extraer_correlativo_de_rango
    db = SessionLocal()
    try:
        listos = db.query(OrdenServicio).filter(OrdenServicio.estado == "LISTO PARA ENTREGAR").count()

        factura_alerta = None
        cfg_fact = db.get(ConfiguracionFacturacion, 1)
        if cfg_fact and cfg_fact.rango_autorizado_fin:
            limite = extraer_correlativo_de_rango(cfg_fact.rango_autorizado_fin)
            if limite is not None:
                siguiente = (cfg_fact.correlativo_fiscal_actual or 0) + 1
                restantes = max(limite - siguiente + 1, 0)
                umbral = cfg_fact.alerta_umbral_fiscal if cfg_fact.alerta_umbral_fiscal is not None else 50
                if restantes <= umbral:
                    factura_alerta = {
                        "restantes": restantes, "umbral": umbral,
                        "rango_fin": cfg_fact.rango_autorizado_fin,
                        "agotado": restantes <= 0,
                    }

        return {"listos_entregar": listos, "factura_alerta": factura_alerta}
    finally:
        db.close()


def fmt_tojson(valor):
    # Seguro dentro de <script>: un texto con "</script>" no rompe la página.
    texto = json.dumps(valor).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return Markup(texto)


templates.env.filters["tojson"] = fmt_tojson
templates.env.filters["moneda"] = fmt_moneda
templates.env.filters["fecha"] = fmt_fecha
templates.env.globals["get_flashes"] = obtener_flashes
templates.env.globals["config_taller"] = obtener_config_actual
templates.env.globals["notificaciones_taller"] = obtener_notificaciones
templates.env.globals["version_estatico"] = version_estatico


def estado_caja():
    """Estado de la apertura de caja para el aviso de la barra superior
    (ver app/utils/turnos_caja.py). Nunca lanza error."""
    from app.utils.turnos_caja import estado_caja_para_plantilla
    return estado_caja_para_plantilla()


templates.env.globals["estado_caja"] = estado_caja


def fmt_hora_local(valor, formato="%d/%m/%Y %I:%M %p"):
    """Fecha/hora guardada en UTC -> hora de Honduras, con formato."""
    if not valor:
        return ""
    from app.utils.turnos_caja import a_hora_local
    try:
        return a_hora_local(valor).strftime(formato)
    except (AttributeError, TypeError, ValueError):
        return str(valor)


templates.env.filters["hn"] = fmt_hora_local


# Nombre legible de los estados de orden (con tildes y en minúscula).
ESTADOS_LEGIBLES = {
    "RECIBIDO": "Recibido", "EN DIAGNOSTICO": "En diagnóstico", "COTIZADO": "Cotizado",
    "ESPERANDO APROBACION": "Esperando aprobación", "ESPERANDO REPUESTO": "Esperando repuesto",
    "EN REPARACION": "En reparación", "LISTO PARA ENTREGAR": "Listo para entregar",
    "ENTREGADO": "Entregado", "CANCELADO": "Cancelado",
}


def fmt_estado(valor):
    if not valor:
        return ""
    return ESTADOS_LEGIBLES.get(valor, str(valor).capitalize())


templates.env.filters["estado_txt"] = fmt_estado


def notas_recordatorio(usuario_id):
    """Cuántas notas del usuario tienen recordatorio para hoy o ya vencido
    (el número junto a «Notas» en el menú). Nunca lanza error."""
    if not usuario_id:
        return 0
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        from app.routers.notas import contar_recordatorios
        return contar_recordatorios(db, usuario_id)
    except Exception:
        return 0
    finally:
        db.close()


templates.env.globals["notas_recordatorio"] = notas_recordatorio


def bancos_activos_plantilla():
    """Bancos activos para los selectores (el principal primero). Nunca lanza error."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        from app.utils.bancos import bancos_activos
        return [{"id": b.id, "nombre": b.nombre, "etiqueta": b.etiqueta, "principal": b.principal} for b in bancos_activos(db)]
    except Exception:
        return []
    finally:
        db.close()


templates.env.globals["bancos_activos"] = bancos_activos_plantilla


def fmt_tipo_mov(valor):
    """«gasto»/«ingreso» guardado -> texto que se muestra (Egreso/Ingreso)."""
    return {"gasto": "Egreso", "ingreso": "Ingreso"}.get((valor or "").lower(), valor or "")


templates.env.filters["tipo_mov"] = fmt_tipo_mov

from app.utils.pantalla_pdf import url_pantalla  # noqa: E402
templates.env.filters["pantalla"] = url_pantalla


def tema_de(usuario):
    """data-tema / data-variante / temporada para <html> (ver app/utils/temas.py)."""
    from app.utils.temas import resolver
    try:
        valor = usuario.get("tema_modo") if isinstance(usuario, dict) else getattr(usuario, "tema_modo", None)
    except Exception:  # noqa: BLE001 - sin usuario (login): tema por defecto
        valor = None
    return resolver(valor if isinstance(valor, str) else "")


templates.env.globals["tema_de"] = tema_de


def ropa_de(usuario):
    """Lo que la mascota lleva puesto hoy (app/utils/ropa_mascota.py)."""
    from app.utils.ropa_mascota import puesta
    try:
        valor = usuario.get("mascota_ropa") if isinstance(usuario, dict) else getattr(usuario, "mascota_ropa", None)
    except Exception:  # noqa: BLE001
        valor = None
    return puesta(valor if isinstance(valor, str) else None)


def svg_ropa_plantilla(mascota, piezas):
    from markupsafe import Markup
    from app.utils.ropa_mascota import svg_ropa
    return Markup(svg_ropa(mascota, piezas or {}))


templates.env.globals["ropa_de"] = ropa_de
templates.env.globals["svg_ropa"] = svg_ropa_plantilla
