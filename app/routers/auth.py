"""Autenticación: login, logout, gestión básica de usuarios (solo admin) y
apariencia personal (cualquier usuario logueado, ver /mi-perfil/apariencia)."""
import re
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.templates_env import templates
from app.database import get_db
from app.models import Usuario, TEMAS_MODO, TEMAS_ACENTO, MASCOTAS_DISPONIBLES, EFECTOS_CIERRE_VENTANA
from app.security import hash_password, verify_password, usuario_actual
from app.deps import roles_required, login_required
from app.utils.flash import flash

router = APIRouter()


def _sesion_desde_usuario(u: Usuario) -> dict:
    """Arma el dict que se guarda en la sesión (cookie) a partir de un
    Usuario de la base de datos. Se usa al iniciar sesión y cada vez que el
    propio usuario cambia algo de su cuenta (apariencia, datos), para que
    el cambio se refleje de inmediato sin tener que volver a loguearse."""
    return {
        "id": u.id, "username": u.username, "nombre_completo": u.nombre_completo, "rol": u.rol,
        "tema_modo": u.tema_modo, "tema_acento": u.tema_acento,
        "tema_color_personalizado": u.tema_color_personalizado, "mascota": u.mascota,
        "efecto_cierre_ventana": u.efecto_cierre_ventana,
        "animar_apertura_ventana": u.animar_apertura_ventana,
        "dock_magnificacion": u.dock_magnificacion,
        "liquid_glass": u.liquid_glass,
        "mascota_ropa": u.mascota_ropa,
    }


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
    request.session["usuario"] = _sesion_desde_usuario(usuario)
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


@router.get("/usuarios/{usuario_id}/editar")
def usuarios_editar_form(usuario_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(roles_required("admin"))):
    u = db.get(Usuario, usuario_id)
    if not u:
        flash(request, "Usuario no encontrado.", "error")
        return RedirectResponse("/usuarios", status_code=303)
    return templates.TemplateResponse("configuracion/usuario_editar.html", {"request": request, "u": u, "usuario": usuario})


@router.post("/usuarios/{usuario_id}/editar")
def usuarios_actualizar(
    usuario_id: int, request: Request,
    username: str = Form(...),
    nombre_completo: str = Form(...),
    rol: str = Form("tecnico"),
    password: str = Form(""),
    db: Session = Depends(get_db),
    usuario=Depends(roles_required("admin")),
):
    u = db.get(Usuario, usuario_id)
    if not u:
        flash(request, "Usuario no encontrado.", "error")
        return RedirectResponse("/usuarios", status_code=303)

    nuevo_username = username.strip().lower()
    if not nuevo_username:
        flash(request, "El nombre de usuario no puede quedar vacío.", "error")
        return RedirectResponse(f"/usuarios/{usuario_id}/editar", status_code=303)
    if nuevo_username != u.username:
        existe = db.query(Usuario).filter(Usuario.username == nuevo_username, Usuario.id != u.id).first()
        if existe:
            flash(request, f"Ya existe otro usuario con el nombre de usuario '{nuevo_username}'.", "error")
            return RedirectResponse(f"/usuarios/{usuario_id}/editar", status_code=303)

    if u.rol == "admin" and rol != "admin":
        otros_admins_activos = db.query(Usuario).filter(
            Usuario.rol == "admin", Usuario.id != u.id, Usuario.activo == True  # noqa: E712
        ).count()
        if otros_admins_activos == 0:
            flash(request, "No puedes quitarle el rol de administrador: es el único administrador activo del sistema.", "error")
            return RedirectResponse(f"/usuarios/{usuario_id}/editar", status_code=303)

    u.username = nuevo_username
    u.nombre_completo = nombre_completo.strip()
    u.rol = rol
    if password.strip():
        u.password_hash = hash_password(password.strip())
    db.commit()

    if usuario["id"] == u.id:
        request.session["usuario"] = _sesion_desde_usuario(u)

    flash(request, f"Usuario '{u.username}' actualizado correctamente.", "success")
    return RedirectResponse("/usuarios", status_code=303)


@router.get("/mi-perfil/apariencia")
def apariencia_form(request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    u = db.get(Usuario, usuario["id"])
    return templates.TemplateResponse("perfil/apariencia.html", {
        "request": request, "usuario": usuario, "u": u,
        "temas_modo": TEMAS_MODO, "temas_acento": TEMAS_ACENTO, "mascotas_disponibles": MASCOTAS_DISPONIBLES,
        "efectos_cierre_ventana": EFECTOS_CIERRE_VENTANA, **_contexto_temas(u),
    })


def _contexto_temas(u) -> dict:
    from app.utils import temas as T
    from app.utils.turnos_caja import hoy_local
    valor = u.tema_modo or "oscuro"
    from app.utils import ropa_mascota as R
    from urllib.parse import urlencode
    ropa = R.leer(u.mascota_ropa)
    return {
        "trajes_hoy": R.TRAJES_TEMPORADA.get(T.temporada_de(hoy_local()) or "", {}),
        "ropero": R.catalogo(), "ropa": ropa, "mascota_activa": R.mascota_visible(u.mascota_ropa, u.rol),
        "ropa_qs": urlencode({**{p: ropa[p] for p in R.PARTES}, "temporada": "1" if ropa["temporada"] else "0"}),
        "temas": T.TEMAS, "grupos": T.GRUPOS, "temporadas_info": T.TEMPORADAS, "fechas_temporadas": T.fechas_temporadas(),
        "temporada_hoy": T.temporada_de(hoy_local()),
        "tema_elegido": "temporada" if T.es_temporada(valor) else (valor if valor in T.TEMAS else "oscuro"),
        "base_temporada": T.base_de_temporada(valor) if T.es_temporada(valor) else (valor if valor in T.TEMAS else "oscuro"),
    }


_ROBOT_PREVIA = None


def _robot_previa() -> str:
    """El robot en pequeño (data URI) para su vista previa: una imagen SVG
    suelta no puede cargar otras imágenes por dirección."""
    global _ROBOT_PREVIA
    if _ROBOT_PREVIA is None:
        import base64
        import io
        from PIL import Image
        im = Image.open("app/static/img/mascota-robot-cuerpo.png").convert("RGBA")
        im.thumbnail((210, 257))
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        _ROBOT_PREVIA = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return _ROBOT_PREVIA


@router.get("/mi-perfil/mascota/{mascota}.svg")
def mascota_previa(mascota: str, request: Request, cabeza: str = "", ojos: str = "", cuello: str = "", mano: str = "",
                   temporada: str = "1", usuario=Depends(login_required)):
    from fastapi.responses import Response
    from markupsafe import Markup
    from app.utils.ropa_mascota import guardar, puesta, svg_ropa
    if mascota not in [m["valor"] for m in MASCOTAS_DISPONIBLES]:
        mascota = "panda"
    from app.utils.ropa_mascota import PIEZAS_TEMPORADA
    piezas = puesta(guardar(cabeza, ojos, cuello, mano, temporada == "1"))
    # Piezas de temporada pedidas directo (la imagen de respaldo de la mascota flotante).
    for parte, valor in (("cabeza", cabeza), ("ojos", ojos), ("cuello", cuello), ("mano", mano)):
        if valor in PIEZAS_TEMPORADA:
            piezas[parte] = valor
    contexto = {"request": request, "_mascota": mascota, "_ropa_svg": Markup(svg_ropa(mascota, piezas)),
                "robot_img": _robot_previa() if mascota == "robot" else ""}
    svg = templates.get_template("partials/mascota_previa.html").render(contexto)
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "private, max-age=600"})


@router.post("/mi-perfil/apariencia")
def apariencia_actualizar(
    request: Request,
    tema_modo: str = Form("oscuro"),
    tema_base_temporada: str = Form(""),
    tema_acento: str = Form("azul"),
    tema_color_personalizado: str = Form(""),
    mascota: str = Form("panda"),
    efecto_cierre_ventana: str = Form("escala"),
    animar_apertura_ventana: bool = Form(False),
    dock_magnificacion: bool = Form(False),
    liquid_glass: bool = Form(False),
    ropa_cabeza: str = Form(""), ropa_ojos: str = Form(""), ropa_cuello: str = Form(""), ropa_mano: str = Form(""),
    ropa_temporada: str = Form(""), mostrar_mascota: str = Form(""),
    db: Session = Depends(get_db),
    usuario=Depends(login_required),
):
    u = db.get(Usuario, usuario["id"])
    if not u:
        flash(request, "Usuario no encontrado.", "error")
        return RedirectResponse("/", status_code=303)

    valores_modo = [m for m in TEMAS_MODO]
    valores_acento = [a["valor"] for a in TEMAS_ACENTO]
    valores_mascota = [m["valor"] for m in MASCOTAS_DISPONIBLES]
    valores_efecto_cierre = [e["valor"] for e in EFECTOS_CIERRE_VENTANA]

    from app.utils.temas import valor_guardado
    u.tema_modo = valor_guardado(tema_modo, tema_base_temporada)
    u.tema_acento = tema_acento if tema_acento in valores_acento else "azul"
    u.mascota = mascota if mascota in valores_mascota else "panda"

    # Efectos de ventana: cada uno es independiente (ver EFECTOS_CIERRE_
    # VENTANA y los demás campos de Usuario). Los checkboxes solo mandan
    # un valor cuando están marcados, así que si no vienen en el form es
    # porque el usuario los desmarcó.
    u.efecto_cierre_ventana = efecto_cierre_ventana if efecto_cierre_ventana in valores_efecto_cierre else "escala"
    u.animar_apertura_ventana = animar_apertura_ventana
    u.dock_magnificacion = dock_magnificacion
    u.liquid_glass = liquid_glass
    from app.utils.ropa_mascota import guardar as guardar_ropa
    u.mascota_ropa = guardar_ropa(ropa_cabeza, ropa_ojos, ropa_cuello, ropa_mano, ropa_temporada == "1",
                                  mostrar=mostrar_mascota == "1")

    color = tema_color_personalizado.strip()
    if u.tema_acento == "personalizado" and color:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            flash(request, "El color personalizado debe ser un color hexadecimal válido, ej. #2563eb.", "error")
            return RedirectResponse("/mi-perfil/apariencia", status_code=303)
        u.tema_color_personalizado = color
    elif u.tema_acento == "personalizado":
        # se eligió "personalizado" pero no mandó ningún color: mantiene el
        # que ya tenía guardado, o cae a un azul por defecto si nunca eligió uno.
        u.tema_color_personalizado = u.tema_color_personalizado or "#2563eb"

    db.commit()
    request.session["usuario"] = _sesion_desde_usuario(u)
    flash(request, "Apariencia actualizada.", "success")
    return RedirectResponse("/mi-perfil/apariencia", status_code=303)


@router.post("/usuarios/{usuario_id}/eliminar")
def usuarios_eliminar(usuario_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(roles_required("admin"))):
    u = db.get(Usuario, usuario_id)
    if not u:
        flash(request, "Usuario no encontrado.", "error")
        return RedirectResponse("/usuarios", status_code=303)
    if u.id == usuario["id"]:
        flash(request, "No puedes eliminar tu propio usuario mientras tienes la sesión iniciada.", "error")
        return RedirectResponse("/usuarios", status_code=303)
    if u.rol == "admin":
        otros_admins = db.query(Usuario).filter(Usuario.rol == "admin", Usuario.id != u.id).count()
        if otros_admins == 0:
            flash(request, "No puedes eliminar al único administrador del sistema.", "error")
            return RedirectResponse("/usuarios", status_code=303)
    nombre = u.username
    db.delete(u)
    db.commit()
    flash(request, f"Usuario '{nombre}' eliminado definitivamente.", "success")
    return RedirectResponse("/usuarios", status_code=303)
