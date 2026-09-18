"""Dependencias reutilizables para las rutas (auth, roles, base de datos)."""
from fastapi import Request
from app.security import usuario_actual


class NoAutenticado(Exception):
    """Se lanza cuando una ruta protegida se visita sin haber iniciado sesión."""
    pass


class SinPermiso(Exception):
    """Se lanza cuando el usuario autenticado no tiene el rol requerido."""
    pass


def get_current_user(request: Request):
    return usuario_actual(request)


def login_required(request: Request):
    usuario = usuario_actual(request)
    if not usuario:
        raise NoAutenticado()
    return usuario


def roles_required(*roles):
    def dependency(request: Request):
        usuario = login_required(request)
        if usuario.get("rol") != "admin" and usuario.get("rol") not in roles:
            raise SinPermiso()
        return usuario
    return dependency
