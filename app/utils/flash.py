"""Mensajes flash (éxito/error) guardados en la sesión para mostrarse una vez."""
from starlette.requests import Request


def flash(request: Request, mensaje: str, categoria: str = "info"):
    mensajes = request.session.get("_flashes", [])
    mensajes.append({"categoria": categoria, "mensaje": mensaje})
    request.session["_flashes"] = mensajes


def obtener_flashes(request: Request):
    mensajes = request.session.pop("_flashes", [])
    return mensajes
