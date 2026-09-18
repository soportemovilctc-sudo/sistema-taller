"""Autenticación: login, logout y gestión básica de usuarios (solo admin)."""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.templates_env import templates
from app.database import get_db
from app.models import Usuario
from app.security import hash_password, verify_password, usuario_actual
from app.deps import roles_required

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    if usuario_actual(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.username == username.strip().lower()).first()
    if not usuario or not usuario.activo or not verify_password(password, usuario.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Usuario o contraseña incorrectos."}, status_code=401)
    request.session["usuario"] = {
        "id": usuario.id,
        "username": usuario.username,
        "nombre_completo": usuario.nombre_completo,
        "rol": usuario.rol,
    }
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/usuarios")
def usuarios_list(request: Request, db: Session = Depends(get_db), usuario=Depends(roles_required("admin"))):
    usuarios = db.query(Usuario).order_by(Usuario.nombre_completo).all()
    return templates.TemplateResponse("configuracion/usuarios.html", {"request": request, "usuarios": usuarios, "usuario": usuario})


@router.post("/usuarios/nuevo")
def usuarios_crear(
    request: Request,
    username: str = Form(...),
    nombre_completo: str = Form(...),
    password: str = Form(...),
    rol: str = Form("tecnico"),
    db: Session = Depends(get_db),
    usuario=Depends(roles_required("admin")),
):
    existe = db.query(Usuario).filter(Usuario.username == username.strip().lower()).first()
    if not existe:
        nuevo = Usuario(
            username=username.strip().lower(),
            nombre_completo=nombre_completo.strip(),
            password_hash=hash_password(password),
            rol=rol,
            activo=True,
        )
        db.add(nuevo)
        db.commit()
    return RedirectResponse("/usuarios", status_code=303)


@router.post("/usuarios/{usuario_id}/toggle")
def usuarios_toggle(usuario_id: int, db: Session = Depends(get_db), usuario=Depends(roles_required("admin"))):
    u = db.get(Usuario, usuario_id)
    if u:
        u.activo = not u.activo
        db.commit()
    return RedirectResponse("/usuarios", status_code=303)
