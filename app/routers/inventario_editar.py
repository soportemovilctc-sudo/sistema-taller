"""Inventario → Editar productos (solo administrador): nombre, categoría,
marca, costo, precio de venta, stock mínimo, caja, proveedor y estado de
muchos productos a la vez, con la opción de escribir costos/precios con ISV.
Cada cambio queda en el historial del producto."""
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.templates_env import templates
from app.database import get_db
from app.deps import roles_required
from app.models import Producto
from app.utils.flash import flash
from app.utils.edicion_productos import validar, aplicar, categorias_validas

router = APIRouter()
URL = "/inventario/editar-varios"
LIMITE = 400


def _consulta(db: Session, q: str, categoria: str, estado: str):
    consulta = db.query(Producto)
    if q.strip():
        like = f"%{q.strip()}%"
        consulta = consulta.filter(or_(Producto.codigo.ilike(like), Producto.nombre.ilike(like),
                                       Producto.marca.ilike(like), Producto.proveedor.ilike(like)))
    if categoria == "__sin__":
        consulta = consulta.filter((Producto.categoria == None) | (Producto.categoria == ""))  # noqa: E711
    elif categoria:
        consulta = consulta.filter(Producto.categoria == categoria)
    if estado in ("activo", "inactivo"):
        consulta = consulta.filter(Producto.estado == estado)
    total = consulta.count()
    return consulta.order_by(Producto.categoria, Producto.nombre).limit(LIMITE).all(), total


def _pantalla(request, db, usuario, q, categoria, estado, valores=None, errores=None, isv=None):
    from app.routers.inventario import _categorias_disponibles, _isv_tasa
    productos, total = _consulta(db, q, categoria, estado)
    return templates.TemplateResponse("inventario/editar_varios.html", {
        "request": request, "usuario": usuario, "productos": productos, "total": total, "limite": LIMITE,
        "q": q, "categoria": categoria, "estado": estado, "categorias": _categorias_disponibles(db),
        "tasa_isv": _isv_tasa(db), "valores": valores or {}, "errores": errores or {}, "isv": isv or {},
    })


@router.get(URL)
def editar_varios(request: Request, q: str = "", categoria: str = "", estado: str = "activo",
                  db: Session = Depends(get_db), usuario=Depends(roles_required("admin"))):
    return _pantalla(request, db, usuario, q, categoria, estado)


@router.post(URL)
async def editar_varios_guardar(request: Request, db: Session = Depends(get_db), usuario=Depends(roles_required("admin"))):
    from app.routers.inventario import _isv_tasa
    form = await request.form()
    q, categoria, estado = form.get("f_q", ""), form.get("f_categoria", ""), form.get("f_estado", "activo")
    costo_con_isv, precio_con_isv = bool(form.get("costo_con_isv")), bool(form.get("precio_con_isv"))
    tasa = _isv_tasa(db)
    cats = categorias_validas(db)
    ids = []
    for x in form.getlist("editado"):
        try:
            ids.append(int(x))
        except ValueError:
            pass
    if not ids:
        flash(request, "No había cambios que guardar.", "success")
        return RedirectResponse(f"{URL}?" + urlencode({"q": q, "categoria": categoria, "estado": estado}), status_code=303)

    errores, valores_form, listos = {}, {}, []
    for pid in dict.fromkeys(ids):
        producto = db.get(Producto, pid)
        if not producto:
            continue
        datos = {c: form.get(f"{c}_{pid}", "") for c in ("nombre", "categoria", "marca", "costo", "precio_venta",
                                                          "stock_minimo", "caja", "proveedor", "estado")}
        valores_form[pid] = datos
        limpios, errs = validar(datos, producto, cats, tasa, costo_con_isv, precio_con_isv)
        if errs:
            errores[pid] = errs
        else:
            listos.append((producto, limpios))

    if errores:
        db.rollback()
        flash(request, f"No se guardó nada: {len(errores)} producto(s) tienen datos por corregir (marcados en rojo). Tus cambios siguen en la pantalla.", "error")
        return _pantalla(request, db, usuario, q, categoria, estado, valores_form, errores,
                         {"costo": costo_con_isv, "precio": precio_con_isv})

    n_productos, n_campos = 0, 0
    for producto, limpios in listos:
        cambiados = aplicar(db, producto, limpios, usuario["nombre_completo"], "editar_varios")
        if cambiados:
            n_productos += 1
            n_campos += len(cambiados)
    db.commit()
    flash(request, f"Listo: {n_productos} producto(s) actualizados ({n_campos} dato(s) cambiados). Quedó en el historial de cada producto."
          if n_productos else "No había cambios que guardar.", "success")
    return RedirectResponse(f"{URL}?" + urlencode({"q": q, "categoria": categoria, "estado": estado}), status_code=303)
