"""Instancia compartida de Jinja2Templates con filtros y funciones globales."""
import json
import os
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from app.utils.flash import obtener_flashes

templates = Jinja2Templates(directory="app/templates")


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
            logo_url = ("/static/uploads/" + os.path.basename(cfg.logo_path)) if cfg.logo_path else None
            return {"nombre_taller": cfg.nombre_taller, "moneda": cfg.moneda, "logo_path": cfg.logo_path, "logo_url": logo_url}
    finally:
        db.close()
    return {"nombre_taller": "Mi Taller", "moneda": "L", "logo_path": None, "logo_url": None}


def fmt_tojson(valor):
    return Markup(json.dumps(valor))


templates.env.filters["tojson"] = fmt_tojson
templates.env.filters["moneda"] = fmt_moneda
templates.env.filters["fecha"] = fmt_fecha
templates.env.globals["get_flashes"] = obtener_flashes
templates.env.globals["config_taller"] = obtener_config_actual
