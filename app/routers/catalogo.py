"""Catálogo de marcas y modelos de equipos (admin): permite agregar marcas y
modelos nuevos que salgan al mercado en el futuro, sin tocar código."""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.templates_env import templates
from app.database import get_db
from app.models import MarcaEquipo, ModeloEquipo
from app.deps import login_required, roles_required
from app.utils.flash import flash

router = APIRouter()


@router.get("/catalogo")
def catalogo_index(request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    marcas = (
        db.query(MarcaEquipo)
        .options(joinedload(MarcaEquipo.modelos))
        .order_by(MarcaEquipo.orden, MarcaEquipo.nombre)
        .all()
    )
    return templates.TemplateResponse("catalogo/index.html", {
        "request": request, "marcas": marcas, "usuario": usuario,
    })


@router.post("/catalogo/marcas/nueva")
def catalogo_marca_crear(
    request: Request, nombre: str = Form(...),
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    nombre = nombre.strip().upper()
    if not nombre:
        flash(request, "El nombre de la marca no puede estar vacío.", "error")
        return RedirectResponse("/catalogo", status_code=303)
    existente = db.query(MarcaEquipo).filter(MarcaEquipo.nombre.ilike(nombre)).first()
    if existente:
        flash(request, f"La marca \"{nombre}\" ya existe.", "error")
        return RedirectResponse("/catalogo", status_code=303)
    maximo_orden = db.query(MarcaEquipo).count()
    db.add(MarcaEquipo(nombre=nombre, orden=maximo_orden, activo=True))
    db.commit()
    flash(request, f"Marca \"{nombre}\" agregada correctamente.", "success")
    return RedirectResponse("/catalogo", status_code=303)


@router.post("/catalogo/marcas/{marca_id}/estado")
def catalogo_marca_toggle(
    marca_id: int, request: Request,
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    marca = db.get(MarcaEquipo, marca_id)
    if marca:
        marca.activo = not marca.activo
        db.commit()
        flash(request, f"Marca \"{marca.nombre}\" {'activada' if marca.activo else 'desactivada'}.", "success")
    return RedirectResponse("/catalogo", status_code=303)


@router.post("/catalogo/marcas/{marca_id}/modelos/nuevo")
def catalogo_modelo_crear(
    marca_id: int, request: Request, nombre: str = Form(...),
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    marca = db.get(MarcaEquipo, marca_id)
    if not marca:
        flash(request, "Marca no encontrada.", "error")
        return RedirectResponse("/catalogo", status_code=303)
    nombre = nombre.strip()
    if not nombre:
        flash(request, "El nombre del modelo no puede estar vacío.", "error")
        return RedirectResponse("/catalogo", status_code=303)
    existente = db.query(ModeloEquipo).filter(
        ModeloEquipo.marca_id == marca_id, ModeloEquipo.nombre.ilike(nombre)
    ).first()
    if existente:
        flash(request, f"El modelo \"{nombre}\" ya existe para {marca.nombre}.", "error")
        return RedirectResponse("/catalogo", status_code=303)
    db.add(ModeloEquipo(marca_id=marca_id, nombre=nombre, activo=True))
    db.commit()
    flash(request, f"Modelo \"{nombre}\" agregado a {marca.nombre}.", "success")
    return RedirectResponse("/catalogo", status_code=303)


@router.post("/catalogo/modelos/{modelo_id}/estado")
def catalogo_modelo_toggle(
    modelo_id: int, request: Request,
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    modelo = db.get(ModeloEquipo, modelo_id)
    if modelo:
        modelo.activo = not modelo.activo
        db.commit()
        flash(request, f"Modelo \"{modelo.nombre}\" {'activado' if modelo.activo else 'desactivado'}.", "success")
    return RedirectResponse("/catalogo", status_code=303)
