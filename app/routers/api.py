"""Endpoints JSON de apoyo: búsqueda global rápida."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models import OrdenServicio, Cliente
from app.deps import login_required

router = APIRouter()


@router.get("/api/buscar")
def buscar_global(q: str = "", db: Session = Depends(get_db), usuario=Depends(login_required)):
    if not q or len(q) < 2:
        return {"ordenes": [], "clientes": []}

    like = f"%{q}%"
    ordenes = db.query(OrdenServicio).join(Cliente).filter(or_(
        OrdenServicio.numero_orden.ilike(like), OrdenServicio.imei.ilike(like),
        OrdenServicio.numero_serie.ilike(like), OrdenServicio.marca.ilike(like),
        OrdenServicio.modelo.ilike(like), OrdenServicio.estado.ilike(like),
        Cliente.nombre.ilike(like), Cliente.telefono.ilike(like),
        Cliente.whatsapp.ilike(like), Cliente.dni.ilike(like),
    )).limit(10).all()

    clientes = db.query(Cliente).filter(or_(
        Cliente.nombre.ilike(like), Cliente.telefono.ilike(like), Cliente.dni.ilike(like),
    )).limit(10).all()

    return {
        "ordenes": [{"id": o.id, "numero_orden": o.numero_orden, "cliente": o.cliente.nombre if o.cliente else "",
                     "estado": o.estado, "equipo": f"{o.marca} {o.modelo}".strip()} for o in ordenes],
        "clientes": [{"id": c.id, "nombre": c.nombre, "telefono": c.telefono} for c in clientes],
    }
