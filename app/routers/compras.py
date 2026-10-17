"""Compras (solo administrador): solicitud de compra -> recepción -> pago.
La lógica está en app/utils/compras.py."""
from decimal import Decimal

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session, selectinload

from app.templates_env import templates
from app.database import get_db
from app.deps import roles_required
from app.models import (
    Producto, MovimientoFinanciero, SolicitudCompra, SolicitudCompraDetalle, RecepcionCompra,
    ESTADOS_COMPRA, FORMAS_PAGO_COMPRA, PAGO_COMPRA_CREDITO, COMPRA_PENDIENTE, COMPRA_PARCIAL,
)
from app.utils.flash import flash
from app.utils.calculations import to_decimal
from app.utils.compras import crear_solicitud, recibir, pagar_recepcion, anular_solicitud, cerrar_solicitud

router = APIRouter()
BASE = "/compras"
solo_admin = roles_required("admin")


def _productos(db: Session):
    return db.query(Producto).filter(Producto.estado == "activo").order_by(Producto.nombre).all()


def _saldos_por_solicitud(db: Session) -> dict:
    saldos = {}
    for r in db.query(RecepcionCompra).all():
        saldo = to_decimal(r.total or 0) - to_decimal(r.pagado or 0)
        if saldo > 0:
            saldos[r.solicitud_id] = saldos.get(r.solicitud_id, Decimal("0.00")) + saldo
    return saldos


@router.get(BASE)
def compras_lista(request: Request, estado: str = "", q: str = "", db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    consulta = db.query(SolicitudCompra).options(selectinload(SolicitudCompra.detalles))
    saldos = _saldos_por_solicitud(db)
    if estado == "por_pagar":
        consulta = consulta.filter(SolicitudCompra.id.in_(list(saldos) or [0]))
    elif estado == "abiertas":
        consulta = consulta.filter(SolicitudCompra.estado.in_([COMPRA_PENDIENTE, COMPRA_PARCIAL]))
    elif estado in ESTADOS_COMPRA:
        consulta = consulta.filter(SolicitudCompra.estado == estado)
    if q.strip():
        like = f"%{q.strip()}%"
        consulta = consulta.filter((SolicitudCompra.numero.ilike(like)) | (SolicitudCompra.proveedor.ilike(like)))
    solicitudes = consulta.order_by(SolicitudCompra.id.desc()).limit(300).all()
    abiertas = db.query(SolicitudCompra).filter(SolicitudCompra.estado.in_([COMPRA_PENDIENTE, COMPRA_PARCIAL])).count()
    return templates.TemplateResponse("compras/lista.html", {
        "request": request, "usuario": usuario, "solicitudes": solicitudes, "saldos": saldos,
        "total_por_pagar": sum(saldos.values(), Decimal("0.00")), "abiertas": abiertas,
        "estado": estado, "q": q, "estados": ESTADOS_COMPRA,
    })


@router.get(BASE + "/nueva")
def compras_nueva(request: Request, producto_id: int = 0, db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    from app.routers.inventario import _categorias_disponibles, _isv_tasa, ultimos_codigos
    proveedores = [p for (p,) in db.query(SolicitudCompra.proveedor).distinct().order_by(SolicitudCompra.proveedor).all() if p]
    return templates.TemplateResponse("compras/nueva.html", {
        "request": request, "usuario": usuario, "productos": _productos(db), "preseleccion": producto_id,
        "categorias": _categorias_disponibles(db), "proveedores": proveedores, "tasa_isv": _isv_tasa(db),
        "ultimos_codigos": ultimos_codigos(db),
    })


@router.post(BASE + "/nueva")
def compras_crear(
    request: Request, proveedor: str = Form(""), notas: str = Form(""),
    producto_id: list[str] = Form([]), cantidad: list[str] = Form([]), costo: list[str] = Form([]),
    precio: list[str] = Form([]), costo_con_isv: bool = Form(False), precio_con_isv: bool = Form(False),
    db: Session = Depends(get_db), usuario=Depends(solo_admin),
):
    from app.routers.inventario import _isv_tasa
    precios = list(precio) + [""] * (len(producto_id) - len(precio))
    lineas = [{"producto_id": p, "cantidad": c, "costo": k, "precio": v}
              for p, c, k, v in zip(producto_id, cantidad, costo, precios) if (p or "").strip()]
    sol, errores = crear_solicitud(db, proveedor, notas, lineas, usuario["nombre_completo"],
                                   costo_con_isv=costo_con_isv, precio_con_isv=precio_con_isv, tasa=_isv_tasa(db))
    if errores:
        db.rollback()
        flash(request, "No se creó la solicitud: " + " ".join(errores), "error")
        return RedirectResponse(BASE + "/nueva", status_code=303)
    db.commit()
    flash(request, f"Solicitud {sol.numero} creada. Cuando llegue la mercadería, confirma la recepción.", "success")
    return RedirectResponse(f"{BASE}/{sol.id}", status_code=303)


@router.post(BASE + "/producto-rapido")
def compras_producto_rapido(
    request: Request, codigo: str = Form(""), nombre: str = Form(""), categoria: str = Form(""),
    precio_venta: str = Form("0"), precio_incluye_isv: bool = Form(False),
    db: Session = Depends(get_db), usuario=Depends(solo_admin),
):
    """Crea un producto nuevo (con 0 unidades) desde la solicitud de compra."""
    from app.routers.inventario import _categoria_valida, _isv_tasa, _quitar_impuesto
    codigo, nombre = codigo.strip(), nombre.strip()
    if not codigo or not nombre:
        return JSONResponse({"ok": False, "mensaje": "Escribe el código y el nombre."}, status_code=400)
    if db.query(Producto).filter(Producto.codigo == codigo).first():
        return JSONResponse({"ok": False, "mensaje": "Ya existe un producto con ese código."}, status_code=400)
    if not _categoria_valida(db, categoria):
        return JSONResponse({"ok": False, "mensaje": "Esa categoría no existe."}, status_code=400)
    try:
        precio = to_decimal(precio_venta or "0")
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "mensaje": "Precio de venta inválido."}, status_code=400)
    if precio_incluye_isv:
        precio = _quitar_impuesto(precio, _isv_tasa(db))
    p = Producto(codigo=codigo, nombre=nombre, categoria=categoria, costo=0, precio_venta=precio,
                 existencia=0, stock_minimo=0, estado="activo")
    db.add(p)
    db.commit()
    return JSONResponse({"ok": True, "id": p.id, "codigo": p.codigo, "nombre": p.nombre, "costo": "0.00", "existencia": 0,
                         "precio": str(p.precio_venta or 0)})


@router.get(BASE + "/{solicitud_id}")
def compras_detalle(solicitud_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    sol = db.get(SolicitudCompra, solicitud_id)
    if not sol:
        flash(request, "Solicitud no encontrada.", "error")
        return RedirectResponse(BASE, status_code=303)
    pagos = {}
    ids = [r.id for r in sol.recepciones]
    if ids:
        for m in db.query(MovimientoFinanciero).filter(MovimientoFinanciero.recepcion_compra_id.in_(ids)).order_by(MovimientoFinanciero.fecha).all():
            pagos.setdefault(m.recepcion_compra_id, []).append(m)
    return templates.TemplateResponse("compras/detalle.html", {
        "request": request, "usuario": usuario, "sol": sol, "pagos": pagos, "estados": ESTADOS_COMPRA,
        "puede_recibir": sol.estado in (COMPRA_PENDIENTE, COMPRA_PARCIAL),
    })


@router.get(BASE + "/{solicitud_id}/recibir")
def compras_recibir_form(solicitud_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    sol = db.get(SolicitudCompra, solicitud_id)
    if not sol or sol.estado not in (COMPRA_PENDIENTE, COMPRA_PARCIAL):
        flash(request, "Esta solicitud ya no se puede recibir.", "error")
        return RedirectResponse(f"{BASE}/{solicitud_id}" if sol else BASE, status_code=303)
    from app.routers.inventario import _isv_tasa
    return templates.TemplateResponse("compras/recibir.html", {
        "request": request, "usuario": usuario, "sol": sol, "formas": FORMAS_PAGO_COMPRA,
        "tasa_isv": _isv_tasa(db),
    })


@router.post(BASE + "/{solicitud_id}/recibir")
async def compras_recibir(solicitud_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    sol = db.get(SolicitudCompra, solicitud_id)
    if not sol:
        return RedirectResponse(BASE, status_code=303)
    from app.routers.inventario import _isv_tasa
    form = await request.form()
    lineas = {d.id: (form.get(f"cantidad_{d.id}", ""), form.get(f"costo_{d.id}", ""), form.get(f"precio_{d.id}", ""))
              for d in sol.detalles}
    rec, errores = recibir(db, sol, lineas, form.get("forma_pago", ""), form.get("factura_proveedor", ""),
                           form.get("isv", ""), form.get("notas", ""), usuario["nombre_completo"],
                           costo_con_isv=bool(form.get("costo_con_isv")), precio_con_isv=bool(form.get("precio_con_isv")),
                           tasa=_isv_tasa(db))
    if errores:
        db.rollback()
        flash(request, "No se registró la recepción: " + " ".join(errores), "error")
        return RedirectResponse(f"{BASE}/{solicitud_id}/recibir", status_code=303)
    db.commit()
    extra = " Quedó por pagar al proveedor." if rec.forma_pago == PAGO_COMPRA_CREDITO else ""
    flash(request, f"Recepción {rec.numero} registrada: entraron {sum(d.cantidad for d in rec.detalles)} unidades al inventario.{extra}", "success")
    return RedirectResponse(f"{BASE}/{solicitud_id}", status_code=303)


@router.post(BASE + "/{solicitud_id}/anular")
def compras_anular(solicitud_id: int, request: Request, motivo: str = Form(""), db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    sol = db.get(SolicitudCompra, solicitud_id)
    if not sol:
        return RedirectResponse(BASE, status_code=303)
    error = anular_solicitud(db, sol, motivo, usuario["nombre_completo"])
    if error:
        flash(request, error, "error")
    else:
        db.commit()
        flash(request, f"Solicitud {sol.numero} anulada.", "success")
    return RedirectResponse(f"{BASE}/{solicitud_id}", status_code=303)


@router.post(BASE + "/{solicitud_id}/cerrar")
def compras_cerrar(solicitud_id: int, request: Request, motivo: str = Form(""), db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    sol = db.get(SolicitudCompra, solicitud_id)
    if not sol:
        return RedirectResponse(BASE, status_code=303)
    error = cerrar_solicitud(db, sol, motivo, usuario["nombre_completo"])
    if error:
        flash(request, error, "error")
    else:
        db.commit()
        flash(request, f"Solicitud {sol.numero} cerrada: lo que faltaba ya no se espera.", "success")
    return RedirectResponse(f"{BASE}/{solicitud_id}", status_code=303)


@router.post(BASE + "/recepcion/{recepcion_id}/pagar")
def compras_pagar(
    recepcion_id: int, request: Request, monto: str = Form(""), forma: str = Form(""), nota: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(solo_admin),
):
    rec = db.get(RecepcionCompra, recepcion_id)
    if not rec:
        return RedirectResponse(BASE, status_code=303)
    error = pagar_recepcion(db, rec, monto, forma, nota, usuario["nombre_completo"])
    if error:
        db.rollback()
        flash(request, error, "error")
    else:
        db.commit()
        flash(request, f"Pago registrado a la compra {rec.numero}.", "success")
    return RedirectResponse(f"{BASE}/{rec.solicitud_id}#rec-{rec.id}", status_code=303)
