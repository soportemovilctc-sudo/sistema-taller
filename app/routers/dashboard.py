"""Panel principal: resumen del taller en tiempo real."""
from datetime import datetime, date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.templates_env import templates
from app.database import get_db
from app.models import OrdenServicio, MovimientoFinanciero, Venta, Producto
from app.deps import login_required

router = APIRouter()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    recibidas_hoy = db.query(OrdenServicio).filter(func.date(OrdenServicio.fecha) == hoy).count()
    en_diagnostico = db.query(OrdenServicio).filter(OrdenServicio.estado == "EN DIAGNOSTICO").count()
    en_reparacion = db.query(OrdenServicio).filter(OrdenServicio.estado == "EN REPARACION").count()
    listas = db.query(OrdenServicio).filter(OrdenServicio.estado == "LISTO PARA ENTREGAR").count()
    entregadas = db.query(OrdenServicio).filter(OrdenServicio.estado == "ENTREGADO").count()

    saldos_pendientes = db.query(func.coalesce(func.sum(OrdenServicio.saldo), 0)).filter(
        OrdenServicio.estado != "CANCELADO"
    ).scalar() or 0

    def suma_movimientos(tipo, desde):
        return db.query(func.coalesce(func.sum(MovimientoFinanciero.monto), 0)).filter(
            MovimientoFinanciero.tipo == tipo, MovimientoFinanciero.fecha >= desde
        ).scalar() or 0

    inicio_hoy = datetime.combine(hoy, datetime.min.time())
    inicio_mes_dt = datetime.combine(inicio_mes, datetime.min.time())

    ingresos_dia = suma_movimientos("ingreso", inicio_hoy)
    gastos_dia = suma_movimientos("gasto", inicio_hoy)
    ingresos_mes = suma_movimientos("ingreso", inicio_mes_dt)
    gastos_mes = suma_movimientos("gasto", inicio_mes_dt)

    ventas_hoy = db.query(func.coalesce(func.sum(Venta.total), 0)).filter(Venta.fecha >= inicio_hoy).scalar() or 0

    stock_bajo = db.query(Producto).filter(
        Producto.estado == "activo", Producto.existencia <= Producto.stock_minimo
    ).all()

    ordenes_recientes = db.query(OrdenServicio).order_by(OrdenServicio.fecha.desc()).limit(8).all()

    # Serie de últimos 7 días para el gráfico de ingresos
    dias = [hoy - timedelta(days=i) for i in range(6, -1, -1)]
    serie_ingresos = []
    for d in dias:
        ini = datetime.combine(d, datetime.min.time())
        fin = datetime.combine(d, datetime.max.time())
        total = db.query(func.coalesce(func.sum(MovimientoFinanciero.monto), 0)).filter(
            MovimientoFinanciero.tipo == "ingreso", MovimientoFinanciero.fecha.between(ini, fin)
        ).scalar() or 0
        serie_ingresos.append({"dia": d.strftime("%d/%m"), "total": float(total)})

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "usuario": usuario,
        "recibidas_hoy": recibidas_hoy, "en_diagnostico": en_diagnostico,
        "en_reparacion": en_reparacion, "listas": listas, "entregadas": entregadas,
        "saldos_pendientes": saldos_pendientes,
        "ingresos_dia": ingresos_dia, "gastos_dia": gastos_dia,
        "ingresos_mes": ingresos_mes, "gastos_mes": gastos_mes,
        "ventas_hoy": ventas_hoy,
        "stock_bajo": stock_bajo,
        "ordenes_recientes": ordenes_recientes,
        "serie_ingresos": serie_ingresos,
    })
