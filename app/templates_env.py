"""Instancia compartida de Jinja2Templates con filtros y funciones globales."""
import json
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
    return Markup(json.dumps(valor))


templates.env.filters["tojson"] = fmt_tojson
templates.env.filters["moneda"] = fmt_moneda
templates.env.filters["fecha"] = fmt_fecha
templates.env.globals["get_flashes"] = obtener_flashes
templates.env.globals["config_taller"] = obtener_config_actual
templates.env.globals["notificaciones_taller"] = obtener_notificaciones
templates.env.globals["version_estatico"] = version_estatico
