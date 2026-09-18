"""Módulo de clientes: crear, editar, buscar y ver historial/resumen."""
from decimal import Decimal
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.templates_env import templates
from app.database import get_db
from app.models import Cliente, OrdenServicio
from app.deps import login_required
from app.utils.flash import flash

router = APIRouter()


@router.get("/clientes")
def clientes_list(request: Request, q: str = "", db: Session = Depends(get_db), usuario=Depends(login_required)):
    query = db.query(Cliente)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Cliente.nombre.ilike(like), Cliente.telefono.ilike(like),
            Cliente.whatsapp.ilike(like), Cliente.dni.ilike(like), Cliente.correo.ilike(like),
        ))
    clientes = query.order_by(Cliente.nombre).all()
    return templates.TemplateResponse("clientes/list.html", {"request": request, "clientes": clientes, "q": q, "usuario": usuario})


@router.get("/clientes/nuevo")
def clientes_nuevo_form(request: Request, usuario=Depends(login_required)):
    return templates.TemplateResponse("clientes/form.html", {"request": request, "cliente": None, "usuario": usuario})


@router.post("/clientes/nuevo")
def clientes_crear(
    request: Request,
    nombre: str = Form(...),
    telefono: str = Form(""),
    whatsapp: str = Form(""),
    dni: str = Form(""),
    rtn: str = Form(""),
    correo: str = Form(""),
    direccion: str = Form(""),
    notas: str = Form(""),
    db: Session = Depends(get_db),
    usuario=Depends(login_required),
):
    cliente = Cliente(nombre=nombre.strip(), telefono=telefono, whatsapp=whatsapp, dni=dni, rtn=rtn,
                       correo=correo, direccion=direccion, notas=notas)
    db.add(cliente)
    db.commit()
    return RedirectResponse(f"/clientes/{cliente.id}", status_code=303)


@router.get("/clientes/{cliente_id}/editar")
def clientes_editar_form(cliente_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        flash(request, "Cliente no encontrado.", "error")
        return RedirectResponse("/clientes", status_code=303)
    return templates.TemplateResponse("clientes/form.html", {"request": request, "cliente": cliente, "usuario": usuario})


@router.post("/clientes/{cliente_id}/editar")
def clientes_actualizar(
    cliente_id: int,
    nombre: str = Form(...),
    telefono: str = Form(""),
    whatsapp: str = Form(""),
    dni: str = Form(""),
    rtn: str = Form(""),
    correo: str = Form(""),
    direccion: str = Form(""),
    notas: str = Form(""),
    db: Session = Depends(get_db),
    usuario=Depends(login_required),
):
    cliente = db.get(Cliente, cliente_id)
    if cliente:
        cliente.nombre = nombre.strip()
        cliente.telefono = telefono
        cliente.whatsapp = whatsapp
        cliente.dni = dni
        cliente.rtn = rtn
        cliente.correo = correo
        cliente.direccion = direccion
        cliente.notas = notas
        db.commit()
    return RedirectResponse(f"/clientes/{cliente_id}", status_code=303)


@router.get("/clientes/{cliente_id}")
def clientes_detalle(cliente_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        flash(request, "Cliente no encontrado.", "error")
        return RedirectResponse("/clientes", status_code=303)
    ordenes = db.query(OrdenServicio).filter(OrdenServicio.cliente_id == cliente_id).order_by(OrdenServicio.fecha.desc()).all()

    total_facturado = sum((o.total or Decimal("0") for o in ordenes), Decimal("0"))
    total_pagado = sum((o.abonado or Decimal("0") for o in ordenes), Decimal("0"))
    saldo_pendiente = sum((o.saldo or Decimal("0") for o in ordenes), Decimal("0"))

    return templates.TemplateResponse("clientes/detail.html", {
        "request": request, "cliente": cliente, "ordenes": ordenes, "usuario": usuario,
        "resumen": {
            "cantidad_ordenes": len(ordenes),
            "total_facturado": total_facturado,
            "total_pagado": total_pagado,
            "saldo_pendiente": saldo_pendiente,
        },
    })
