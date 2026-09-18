"""Utilidades de seguridad: hashing de contraseñas y acceso a la sesión."""
import bcrypt
from fastapi import Request

ROL_ADMIN = "admin"
ROL_TECNICO = "tecnico"
ROL_VENDEDOR = "vendedor"
ROLES = [ROL_ADMIN, ROL_TECNICO, ROL_VENDEDOR]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def usuario_actual(request: Request):
    """Devuelve el usuario guardado en la sesión (dict simple) o None."""
    return request.session.get("usuario")
