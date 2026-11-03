"""Notas: libreta personal de cada usuario (solo la ve quien la escribió).

Cada nota tiene título, texto con formato básico (negrita, colores,
listas...), color de tarjeta, fecha de recordatorio opcional, y se puede
fijar como importante o marcar como hecha."""
from datetime import datetime, date

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.templates_env import templates
from app.database import get_db
from app.models import Nota, COLORES_NOTA
from app.utils.flash import flash
from app.utils.html_notas import limpiar_html_nota
from app.utils.turnos_caja import hoy_local
from app.deps import login_required

router = APIRouter()


def _mia(db: Session, nota_id: int, usuario: dict) -> Nota | None:
    n = db.get(Nota, nota_id)
    return n if n and n.usuario_id == usuario["id"] else None


def _fecha(txt: str) -> date | None:
    try:
        return datetime.strptime((txt or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def contar_recordatorios(db: Session, usuario_id: int) -> int:
    """Notas pendientes con recordatorio para hoy o ya vencido (para el menú)."""
    return db.query(Nota).filter(
        Nota.usuario_id == usuario_id, Nota.hecha == False,  # noqa: E712
        Nota.fecha_recordatorio != None, Nota.fecha_recordatorio <= hoy_local(),  # noqa: E711
    ).count()


@router.get("/notas")
def notas_lista(request: Request, ver: str = "pendientes", q: str = "",
                db: Session = Depends(get_db), usuario=Depends(login_required)):
    base = db.query(Nota).filter(Nota.usuario_id == usuario["id"])
    if q.strip():
        like = f"%{q.strip()}%"
        base = base.filter(or_(Nota.titulo.ilike(like), Nota.contenido_texto.ilike(like)))
    hoy = hoy_local()
    pendientes = base.filter(Nota.hecha == False).all()  # noqa: E712
    hechas_n = base.filter(Nota.hecha == True).count()  # noqa: E712
    if ver == "hechas":
        notas = base.filter(Nota.hecha == True).order_by(Nota.hecha_en.desc().nullslast(), Nota.id.desc()).all()  # noqa: E712
        para_hoy = []
    else:
        ver = "pendientes"
        para_hoy = sorted([n for n in pendientes if n.fecha_recordatorio and n.fecha_recordatorio <= hoy],
                          key=lambda n: (n.fecha_recordatorio, not n.importante))
        resto = [n for n in pendientes if n not in para_hoy]
        notas = sorted(resto, key=lambda n: (not n.importante, n.fecha_recordatorio or date.max, -(n.actualizada or n.creada).timestamp()))
    return templates.TemplateResponse("notas/index.html", {
        "request": request, "usuario": usuario, "notas": notas, "para_hoy": para_hoy,
        "ver": ver, "q": q, "hoy": hoy, "n_pendientes": len(pendientes), "n_hechas": hechas_n,
        "colores": COLORES_NOTA,
    })


@router.get("/notas/nueva")
def notas_nueva(request: Request, usuario=Depends(login_required)):
    return templates.TemplateResponse("notas/form.html", {
        "request": request, "usuario": usuario, "nota": None, "colores": COLORES_NOTA,
    })


def _guardar(nota: Nota, titulo: str, contenido: str, color: str, importante: str, fecha_recordatorio: str) -> str | None:
    html, texto = limpiar_html_nota(contenido)
    titulo = (titulo or "").strip()[:150]
    if not titulo and not texto:
        return "Escribe un título o algo en la nota."
    nota.titulo = titulo
    nota.contenido = html
    nota.contenido_texto = texto
    nota.color = color if color in COLORES_NOTA else ""
    nota.importante = importante == "1"
    nota.fecha_recordatorio = _fecha(fecha_recordatorio)
    nota.actualizada = datetime.utcnow()
    return None


@router.post("/notas/nueva")
def notas_crear(request: Request, titulo: str = Form(""), contenido: str = Form(""), color: str = Form(""),
                importante: str = Form(""), fecha_recordatorio: str = Form(""),
                db: Session = Depends(get_db), usuario=Depends(login_required)):
    nota = Nota(usuario_id=usuario["id"], creada=datetime.utcnow())
    error = _guardar(nota, titulo, contenido, color, importante, fecha_recordatorio)
    if error:
        flash(request, error, "error")
        return RedirectResponse("/notas/nueva", status_code=303)
    db.add(nota)
    db.commit()
    flash(request, "Nota guardada.", "success")
    return RedirectResponse("/notas", status_code=303)


@router.get("/notas/{nota_id}/editar")
def notas_editar_form(nota_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    nota = _mia(db, nota_id, usuario)
    if not nota:
        flash(request, "Esa nota no existe.", "error")
        return RedirectResponse("/notas", status_code=303)
    return templates.TemplateResponse("notas/form.html", {
        "request": request, "usuario": usuario, "nota": nota, "colores": COLORES_NOTA,
    })


@router.post("/notas/{nota_id}/editar")
def notas_editar(nota_id: int, request: Request, titulo: str = Form(""), contenido: str = Form(""), color: str = Form(""),
                 importante: str = Form(""), fecha_recordatorio: str = Form(""),
                 db: Session = Depends(get_db), usuario=Depends(login_required)):
    nota = _mia(db, nota_id, usuario)
    if not nota:
        flash(request, "Esa nota no existe.", "error")
        return RedirectResponse("/notas", status_code=303)
    error = _guardar(nota, titulo, contenido, color, importante, fecha_recordatorio)
    if error:
        flash(request, error, "error")
        return RedirectResponse(f"/notas/{nota_id}/editar", status_code=303)
    db.commit()
    flash(request, "Nota actualizada.", "success")
    return RedirectResponse("/notas", status_code=303)


def _volver(volver: str) -> str:
    return volver if volver.startswith("/notas") else "/notas"


@router.post("/notas/{nota_id}/hecha")
def notas_hecha(nota_id: int, request: Request, volver: str = Form("/notas"),
                db: Session = Depends(get_db), usuario=Depends(login_required)):
    nota = _mia(db, nota_id, usuario)
    if nota:
        nota.hecha = not nota.hecha
        nota.hecha_en = datetime.utcnow() if nota.hecha else None
        db.commit()
        flash(request, "Nota marcada como hecha." if nota.hecha else "La nota volvió a pendientes.", "success")
    return RedirectResponse(_volver(volver), status_code=303)


@router.post("/notas/{nota_id}/importante")
def notas_importante(nota_id: int, request: Request, volver: str = Form("/notas"),
                     db: Session = Depends(get_db), usuario=Depends(login_required)):
    nota = _mia(db, nota_id, usuario)
    if nota:
        nota.importante = not nota.importante
        db.commit()
    return RedirectResponse(_volver(volver), status_code=303)


@router.post("/notas/{nota_id}/eliminar")
def notas_eliminar(nota_id: int, request: Request, volver: str = Form("/notas"),
                   db: Session = Depends(get_db), usuario=Depends(login_required)):
    nota = _mia(db, nota_id, usuario)
    if nota:
        db.delete(nota)
        db.commit()
        flash(request, "Nota eliminada.", "success")
    return RedirectResponse(_volver(volver), status_code=303)
