"""Módulo de catálogo de servicios: trabajos con nombre propio que ofrece
el taller (ej. "Cambio de pantalla", "Formateo"), cada uno con un precio
de venta y, opcionalmente, un costo (no todos los servicios lo tienen).
Desde una orden se pueden agregar servicios de este catálogo (ver
app/routers/ordenes.py), y Reportes calcula su utilidad a partir de ahí."""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.templates_env import templates
from app.database import get_db
from app.models import Servicio, OrdenServicioExtra
from app.utils.calculations import to_decimal
from app.utils.flash import flash
from app.deps import login_required, roles_required

router = APIRouter()


@router.get("/servicios")
def servicios_list(request: Request, q: str = "", db: Session = Depends(get_db), usuario=Depends(login_required)):
    query = db.query(Servicio)
    if q:
        query = query.filter(Servicio.nombre.ilike(f"%{q}%"))
    servicios = query.order_by(Servicio.nombre).all()
    return templates.TemplateResponse("servicios/list.html", {
        "request": request, "usuario": usuario, "servicios": servicios, "q": q,
    })


@router.get("/servicios/nuevo")
def servicios_nuevo_form(request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    return templates.TemplateResponse("servicios/form.html", {
        "request": request, "servicio": None, "usuario": usuario,
    })


def _validar_formulario(nombre: str, precio_venta: str, costo: str):
    """Valida y convierte los campos del formulario. Devuelve
    (nombre_limpio, precio_dec, costo_dec_o_none, error). El costo es
    simplemente un campo opcional: si se deja en blanco, el servicio
    queda sin costo; si se escribe un número (incluyendo 0), ese es su
    costo. No hace falta ninguna casilla aparte para esto."""
    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        return None, None, None, "El nombre del servicio es obligatorio."
    precio_dec = to_decimal(precio_venta or 0)
    if precio_dec < 0:
        return None, None, None, "El precio de venta no puede ser negativo."
    costo_raw = (costo or "").strip()
    costo_dec = None
    if costo_raw:
        costo_dec = to_decimal(costo_raw)
        if costo_dec < 0:
            return None, None, None, "El costo no puede ser negativo."
    return nombre_limpio, precio_dec, costo_dec, None


@router.post("/servicios/nuevo")
def servicios_crear(
    request: Request,
    nombre: str = Form(...), descripcion: str = Form(""), categoria: str = Form(""),
    precio_venta: str = Form("0"), costo: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    nombre_limpio, precio_dec, costo_dec, error = _validar_formulario(nombre, precio_venta, costo)
    if error:
        flash(request, error, "error")
        return RedirectResponse("/servicios/nuevo", status_code=303)

    existe = db.query(Servicio).filter(Servicio.nombre.ilike(nombre_limpio)).first()
    if existe:
        flash(request, f"Ya existe un servicio llamado '{existe.nombre}'.", "error")
        return RedirectResponse("/servicios/nuevo", status_code=303)

    db.add(Servicio(
        nombre=nombre_limpio, descripcion=descripcion.strip(), categoria=categoria.strip(),
        precio_venta=precio_dec, costo=costo_dec, activo=True,
    ))
    db.commit()
    flash(request, f"Servicio '{nombre_limpio}' creado correctamente.", "success")
    return RedirectResponse("/servicios", status_code=303)


@router.get("/servicios/{servicio_id}/editar")
def servicios_editar_form(servicio_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    servicio = db.get(Servicio, servicio_id)
    if not servicio:
        flash(request, "Servicio no encontrado.", "error")
        return RedirectResponse("/servicios", status_code=303)
    return templates.TemplateResponse("servicios/form.html", {
        "request": request, "servicio": servicio, "usuario": usuario,
    })


@router.post("/servicios/{servicio_id}/editar")
def servicios_actualizar(
    servicio_id: int, request: Request,
    nombre: str = Form(...), descripcion: str = Form(""), categoria: str = Form(""),
    precio_venta: str = Form("0"), costo: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    servicio = db.get(Servicio, servicio_id)
    if not servicio:
        flash(request, "Servicio no encontrado.", "error")
        return RedirectResponse("/servicios", status_code=303)

    nombre_limpio, precio_dec, costo_dec, error = _validar_formulario(nombre, precio_venta, costo)
    if error:
        flash(request, error, "error")
        return RedirectResponse(f"/servicios/{servicio_id}/editar", status_code=303)

    existe = db.query(Servicio).filter(Servicio.nombre.ilike(nombre_limpio), Servicio.id != servicio_id).first()
    if existe:
        flash(request, f"Ya existe otro servicio llamado '{existe.nombre}'.", "error")
        return RedirectResponse(f"/servicios/{servicio_id}/editar", status_code=303)

    servicio.nombre = nombre_limpio
    servicio.descripcion = descripcion.strip()
    servicio.categoria = categoria.strip()
    servicio.precio_venta = precio_dec
    servicio.costo = costo_dec
    db.commit()
    flash(request, f"Servicio '{nombre_limpio}' actualizado correctamente.", "success")
    return RedirectResponse("/servicios", status_code=303)


@router.post("/servicios/{servicio_id}/activar")
def servicios_toggle(servicio_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    servicio = db.get(Servicio, servicio_id)
    if servicio:
        servicio.activo = not servicio.activo
        db.commit()
        flash(request, f"Servicio '{servicio.nombre}' {'activado' if servicio.activo else 'desactivado'}.", "success")
    return RedirectResponse("/servicios", status_code=303)


@router.post("/servicios/{servicio_id}/eliminar")
def servicios_eliminar(
    servicio_id: int, request: Request,
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    """Solo se puede eliminar un servicio que nunca se haya usado en
    ninguna orden; si ya se usó, hay que desactivarlo en vez de borrarlo
    (igual que las categorías de Inventario), para no perder el historial
    de órdenes/facturas/reportes que ya lo referencian."""
    servicio = db.get(Servicio, servicio_id)
    if not servicio:
        return RedirectResponse("/servicios", status_code=303)
    en_uso = db.query(OrdenServicioExtra).filter(OrdenServicioExtra.servicio_id == servicio_id).count()
    if en_uso > 0:
        flash(request, f"No se puede eliminar '{servicio.nombre}': se usó en {en_uso} orden(es). Desactívalo en vez de eliminarlo.", "error")
        return RedirectResponse("/servicios", status_code=303)
    db.delete(servicio)
    db.commit()
    flash(request, f"Servicio '{servicio.nombre}' eliminado.", "success")
    return RedirectResponse("/servicios", status_code=303)
