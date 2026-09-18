"""Módulo de inventario: productos, entradas, salidas, ajustes y alertas de stock."""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.templates_env import templates
from app.database import get_db
from app.models import Producto, MovimientoInventario
from app.utils.calculations import to_decimal
from app.utils.flash import flash
from app.deps import login_required, roles_required

router = APIRouter()


@router.get("/inventario")
def inventario_list(request: Request, q: str = "", db: Session = Depends(get_db), usuario=Depends(login_required)):
    query = db.query(Producto)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Producto.codigo.ilike(like), Producto.nombre.ilike(like),
                                  Producto.categoria.ilike(like), Producto.marca.ilike(like)))
    productos = query.order_by(Producto.nombre).all()
    stock_bajo_ids = {p.id for p in productos if p.existencia <= p.stock_minimo}
    return templates.TemplateResponse("inventario/list.html", {
        "request": request, "productos": productos, "q": q, "usuario": usuario, "stock_bajo_ids": stock_bajo_ids,
    })


@router.get("/inventario/nuevo")
def inventario_nuevo_form(request: Request, usuario=Depends(login_required)):
    return templates.TemplateResponse("inventario/form.html", {"request": request, "producto": None, "usuario": usuario})


@router.post("/inventario/nuevo")
def inventario_crear(
    request: Request,
    codigo: str = Form(...), nombre: str = Form(...), categoria: str = Form(""), marca: str = Form(""),
    costo: str = Form("0"), precio_venta: str = Form("0"), existencia: int = Form(0),
    stock_minimo: int = Form(0), proveedor: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    existe = db.query(Producto).filter(Producto.codigo == codigo.strip()).first()
    if existe:
        flash(request, "Ya existe un producto con ese código.", "error")
        return RedirectResponse("/inventario/nuevo", status_code=303)
    producto = Producto(
        codigo=codigo.strip(), nombre=nombre.strip(), categoria=categoria, marca=marca,
        costo=to_decimal(costo), precio_venta=to_decimal(precio_venta),
        existencia=max(0, existencia), stock_minimo=max(0, stock_minimo), proveedor=proveedor, estado="activo",
    )
    db.add(producto)
    db.commit()
    flash(request, "Producto creado correctamente.", "success")
    return RedirectResponse("/inventario", status_code=303)


@router.get("/inventario/{producto_id}/editar")
def inventario_editar_form(producto_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    producto = db.get(Producto, producto_id)
    if not producto:
        flash(request, "Producto no encontrado.", "error")
        return RedirectResponse("/inventario", status_code=303)
    return templates.TemplateResponse("inventario/form.html", {"request": request, "producto": producto, "usuario": usuario})


@router.post("/inventario/{producto_id}/editar")
def inventario_actualizar(
    producto_id: int, request: Request,
    nombre: str = Form(...), categoria: str = Form(""), marca: str = Form(""),
    costo: str = Form("0"), precio_venta: str = Form("0"), stock_minimo: int = Form(0),
    proveedor: str = Form(""), estado: str = Form("activo"),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    producto = db.get(Producto, producto_id)
    if producto:
        producto.nombre = nombre.strip()
        producto.categoria = categoria
        producto.marca = marca
        producto.costo = to_decimal(costo)
        producto.precio_venta = to_decimal(precio_venta)
        producto.stock_minimo = max(0, stock_minimo)
        producto.proveedor = proveedor
        producto.estado = estado
        db.commit()
        flash(request, "Producto actualizado.", "success")
    return RedirectResponse("/inventario", status_code=303)


@router.get("/inventario/{producto_id}/movimiento")
def inventario_movimiento_form(producto_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    producto = db.get(Producto, producto_id)
    if not producto:
        flash(request, "Producto no encontrado.", "error")
        return RedirectResponse("/inventario", status_code=303)
    movimientos = db.query(MovimientoInventario).filter(MovimientoInventario.producto_id == producto_id).order_by(MovimientoInventario.fecha.desc()).all()
    return templates.TemplateResponse("inventario/movimiento.html", {
        "request": request, "producto": producto, "movimientos": movimientos, "usuario": usuario,
    })


@router.post("/inventario/{producto_id}/movimiento")
def inventario_registrar_movimiento(
    producto_id: int, request: Request,
    tipo: str = Form(...), cantidad: int = Form(...), motivo: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    producto = db.get(Producto, producto_id)
    if not producto:
        return RedirectResponse("/inventario", status_code=303)

    if cantidad <= 0:
        flash(request, "La cantidad debe ser mayor a cero.", "error")
        return RedirectResponse(f"/inventario/{producto_id}/movimiento", status_code=303)

    if tipo == "entrada":
        nueva_existencia = producto.existencia + cantidad
    elif tipo == "salida":
        if cantidad > producto.existencia:
            flash(request, "No hay suficiente existencia para esa salida.", "error")
            return RedirectResponse(f"/inventario/{producto_id}/movimiento", status_code=303)
        nueva_existencia = producto.existencia - cantidad
    elif tipo == "ajuste":
        nueva_existencia = cantidad  # el ajuste define la existencia final directamente
        if nueva_existencia < 0:
            flash(request, "La existencia no puede quedar negativa.", "error")
            return RedirectResponse(f"/inventario/{producto_id}/movimiento", status_code=303)
    else:
        flash(request, "Tipo de movimiento inválido.", "error")
        return RedirectResponse(f"/inventario/{producto_id}/movimiento", status_code=303)

    movimiento = MovimientoInventario(
        producto_id=producto.id, tipo=tipo, cantidad=cantidad, existencia_resultante=nueva_existencia,
        usuario_nombre=usuario["nombre_completo"], motivo=motivo,
    )
    producto.existencia = nueva_existencia
    db.add(movimiento)
    db.commit()
    flash(request, "Movimiento de inventario registrado.", "success")
    return RedirectResponse(f"/inventario/{producto_id}/movimiento", status_code=303)
