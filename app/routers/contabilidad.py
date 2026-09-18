"""Contabilidad básica: ingresos y gastos, con filtros por período."""
from datetime import datetime, date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.templates_env import templates
from app.database import get_db
from app.models import MovimientoFinanciero
from app.utils.calculations import to_decimal
from app.utils.flash import flash
from app.deps import login_required

router = APIRouter()

CATEGORIAS_GASTO = ["Compras", "Servicios", "Transporte", "Herramientas", "Otros gastos"]
CATEGORIAS_INGRESO = ["Pago de reparación", "Venta POS", "Otros ingresos"]


def _rango_fechas(periodo: str, desde: str, hasta: str):
    hoy = date.today()
    if periodo == "dia":
        return datetime.combine(hoy, datetime.min.time()), datetime.combine(hoy, datetime.max.time())
    if periodo == "semana":
        inicio = hoy - timedelta(days=hoy.weekday())
        return datetime.combine(inicio, datetime.min.time()), datetime.combine(hoy, datetime.max.time())
    if periodo == "mes":
        inicio = hoy.replace(day=1)
        return datetime.combine(inicio, datetime.min.time()), datetime.combine(hoy, datetime.max.time())
    if periodo == "rango" and desde and hasta:
        return (datetime.strptime(desde, "%Y-%m-%d"),
                datetime.combine(datetime.strptime(hasta, "%Y-%m-%d").date(), datetime.max.time()))
    # por defecto: mes actual
    inicio = hoy.replace(day=1)
    return datetime.combine(inicio, datetime.min.time()), datetime.combine(hoy, datetime.max.time())


@router.get("/contabilidad")
def contabilidad_index(
    request: Request, periodo: str = "mes", desde: str = "", hasta: str = "",
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    ini, fin = _rango_fechas(periodo, desde, hasta)
    movimientos = db.query(MovimientoFinanciero).filter(
        MovimientoFinanciero.fecha.between(ini, fin)
    ).order_by(MovimientoFinanciero.fecha.desc()).all()

    ingresos = sum((m.monto for m in movimientos if m.tipo == "ingreso"), Decimal("0"))
    gastos = sum((m.monto for m in movimientos if m.tipo == "gasto"), Decimal("0"))
    balance = ingresos - gastos

    return templates.TemplateResponse("contabilidad/index.html", {
        "request": request, "movimientos": movimientos, "usuario": usuario,
        "periodo": periodo, "desde": desde, "hasta": hasta,
        "ingresos": ingresos, "gastos": gastos, "balance": balance,
        "categorias_gasto": CATEGORIAS_GASTO, "categorias_ingreso": CATEGORIAS_INGRESO,
    })


@router.post("/contabilidad/nuevo")
def contabilidad_crear(
    request: Request,
    tipo: str = Form(...), categoria: str = Form(...), monto: str = Form(...),
    descripcion: str = Form(""), db: Session = Depends(get_db), usuario=Depends(login_required),
):
    try:
        monto_dec = to_decimal(monto)
        if monto_dec <= 0:
            raise ValueError("El monto debe ser mayor a cero.")
    except ValueError as e:
        flash(request, str(e), "error")
        return RedirectResponse("/contabilidad", status_code=303)

    db.add(MovimientoFinanciero(
        tipo=tipo, categoria=categoria, monto=monto_dec, descripcion=descripcion,
        usuario_nombre=usuario["nombre_completo"],
    ))
    db.commit()
    flash(request, "Movimiento registrado correctamente.", "success")
    return RedirectResponse("/contabilidad", status_code=303)
