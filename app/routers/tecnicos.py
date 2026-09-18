"""Módulo de técnicos: crear, editar, activar/desactivar."""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.templates_env import templates
from app.database import get_db
from app.models import Tecnico
from app.deps import roles_required

router = APIRouter()


@router.get("/tecnicos")
def tecnicos_list(request: Request, db: Session = Depends(get_db), usuario=Depends(roles_required("admin"))):
    tecnicos = db.query(Tecnico).order_by(Tecnico.nombre).all()
    return templates.TemplateResponse("tecnicos/list.html", {"request": request, "tecnicos": tecnicos, "usuario": usuario})


@router.post("/tecnicos/nuevo")
def tecnicos_crear(nombre: str = Form(...), telefono: str = Form(""), db: Session = Depends(get_db),
                    usuario=Depends(roles_required("admin"))):
    db.add(Tecnico(nombre=nombre.strip(), telefono=telefono, activo=True))
    db.commit()
    return RedirectResponse("/tecnicos", status_code=303)


@router.post("/tecnicos/{tecnico_id}/editar")
def tecnicos_editar(tecnico_id: int, nombre: str = Form(...), telefono: str = Form(""),
                     db: Session = Depends(get_db), usuario=Depends(roles_required("admin"))):
    t = db.get(Tecnico, tecnico_id)
    if t:
        t.nombre = nombre.strip()
        t.telefono = telefono
        db.commit()
    return RedirectResponse("/tecnicos", status_code=303)


@router.post("/tecnicos/{tecnico_id}/toggle")
def tecnicos_toggle(tecnico_id: int, db: Session = Depends(get_db), usuario=Depends(roles_required("admin"))):
    t = db.get(Tecnico, tecnico_id)
    if t:
        t.activo = not t.activo
        db.commit()
    return RedirectResponse("/tecnicos", status_code=303)
