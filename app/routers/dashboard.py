"""Panel principal: resumen del taller en tiempo real."""
import math
from datetime import datetime, date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.templates_env import templates
from app.database import get_db
from app.models import OrdenServicio, MovimientoFinanciero, Venta, Producto, Configuracion, Tecnico
from app.deps import login_required

# Paleta reutilizada en las gráficas del dashboard (dona, barras).
_COLORES_GRAFICAS = ["#4c8dff", "#34d399", "#f5a623", "#a78bfa", "#38bdf8", "#f2545b", "#5c6884"]

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

    # Órdenes activas que llevan demasiados días en el taller (aviso de
    # atención urgente + modal al entrar al Dashboard).
    cfg_general = db.get(Configuracion, 1)
    umbral_vencido = cfg_general.dias_vencido_alerta if cfg_general else 3
    activas = db.query(OrdenServicio).filter(
        OrdenServicio.estado.notin_(["ENTREGADO", "CANCELADO"])
    ).all()
    todas_vencidas = sorted(
        [o for o in activas if o.dias_en_taller() >= umbral_vencido],
        key=lambda o: o.dias_en_taller(), reverse=True,
    )
    total_vencidas = len(todas_vencidas)
    ordenes_vencidas = todas_vencidas[:10]

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

    # Serie de últimos 6 meses: cuántas órdenes se recibieron cada mes
    # (para la gráfica de tendencia del dashboard).
    meses_serie = []
    cursor_mes = date(hoy.year, hoy.month, 1)
    for _ in range(6):
        meses_serie.append(cursor_mes)
        cursor_mes = (cursor_mes - timedelta(days=1)).replace(day=1)
    meses_serie.reverse()
    serie_mensual = []
    nombres_mes = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    for m in meses_serie:
        if m.month == 12:
            siguiente = date(m.year + 1, 1, 1)
        else:
            siguiente = date(m.year, m.month + 1, 1)
        cantidad = db.query(OrdenServicio).filter(
            OrdenServicio.fecha >= datetime.combine(m, datetime.min.time()),
            OrdenServicio.fecha < datetime.combine(siguiente, datetime.min.time()),
        ).count()
        serie_mensual.append({"mes": nombres_mes[m.month - 1], "total": cantidad})

    # Coordenadas SVG ya calculadas en Python (más simple y confiable que
    # hacer la geometría dentro de la plantilla Jinja).
    _CHART_W, _CHART_H, _PAD_TOP, _PAD_BOTTOM = 560, 160, 14, 26
    _PLOT_H = _CHART_H - _PAD_TOP - _PAD_BOTTOM
    _n_meses = len(serie_mensual)
    _max_mensual = max([p["total"] for p in serie_mensual] + [1])
    _step = (_CHART_W / (_n_meses - 1)) if _n_meses > 1 else 0
    _puntos = []
    for i, p in enumerate(serie_mensual):
        x = round(i * _step, 1)
        y = round(_PAD_TOP + _PLOT_H - ((p["total"] / _max_mensual * _PLOT_H) if _max_mensual else 0), 1)
        _puntos.append({"x": x, "y": y, "mes": p["mes"], "total": p["total"]})
    _baseline_y = _PAD_TOP + _PLOT_H
    _line_path = "M " + " L ".join(f"{pt['x']},{pt['y']}" for pt in _puntos) if _puntos else ""
    _area_path = (
        _line_path + f" L {_puntos[-1]['x']},{_baseline_y} L {_puntos[0]['x']},{_baseline_y} Z"
        if _puntos else ""
    )
    chart_mensual = {
        "width": _CHART_W, "height": _CHART_H, "baseline_y": _baseline_y,
        "puntos": _puntos, "line_path": _line_path, "area_path": _area_path,
    }

    # Mezcla de tipos de equipo recibidos (para la gráfica de dona).
    filas_tipo = db.query(OrdenServicio.tipo_equipo, func.count(OrdenServicio.id)).group_by(
        OrdenServicio.tipo_equipo
    ).order_by(func.count(OrdenServicio.id).desc()).all()
    total_equipos = sum(c for _, c in filas_tipo) or 1
    _circunferencia = round(2 * math.pi * 54, 2)
    _acumulado_pct = 0
    mix_tipo_equipo = []
    for i, (tipo, cantidad) in enumerate(filas_tipo):
        pct = round(cantidad / total_equipos * 100)
        mix_tipo_equipo.append({
            "tipo": (tipo or "Otro"), "cantidad": cantidad, "pct": pct,
            "color": _COLORES_GRAFICAS[i % len(_COLORES_GRAFICAS)],
            "dasharray": f"{round(cantidad / total_equipos * _circunferencia, 2)} {_circunferencia}",
            "dashoffset": round(-(_acumulado_pct / 100 * _circunferencia), 2),
        })
        _acumulado_pct += pct

    # Marcas más reparadas (top 6, excluyendo vacías).
    filas_marca = db.query(OrdenServicio.marca, func.count(OrdenServicio.id)).filter(
        OrdenServicio.marca.isnot(None), OrdenServicio.marca != ""
    ).group_by(OrdenServicio.marca).order_by(func.count(OrdenServicio.id).desc()).limit(6).all()
    max_marca = max([c for _, c in filas_marca], default=0) or 1
    top_marcas = [
        {"marca": marca, "cantidad": cantidad, "pct": round(cantidad / max_marca * 100)}
        for marca, cantidad in filas_marca
    ]

    # Desempeño por técnico: órdenes activas asignadas y entregadas en total.
    tecnicos_activos = db.query(Tecnico).filter(Tecnico.activo == True).order_by(Tecnico.nombre).all()  # noqa: E712
    tecnicos_desempeno = []
    for t in tecnicos_activos:
        activas = db.query(OrdenServicio).filter(
            OrdenServicio.tecnico_id == t.id, OrdenServicio.estado.notin_(["ENTREGADO", "CANCELADO"])
        ).count()
        entregadas_t = db.query(OrdenServicio).filter(
            OrdenServicio.tecnico_id == t.id, OrdenServicio.estado == "ENTREGADO"
        ).count()
        if activas or entregadas_t:
            tecnicos_desempeno.append({
                "nombre": t.nombre, "activas": activas, "entregadas": entregadas_t,
                "iniciales": "".join([p[0] for p in t.nombre.split()[:2]]).upper(),
            })
    tecnicos_desempeno.sort(key=lambda x: (x["activas"], x["entregadas"]), reverse=True)

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
        "ordenes_vencidas": ordenes_vencidas,
        "total_vencidas": total_vencidas,
        "umbral_vencido": umbral_vencido,
        "serie_mensual": serie_mensual,
        "chart_mensual": chart_mensual,
        "mix_tipo_equipo": mix_tipo_equipo,
        "top_marcas": top_marcas,
        "tecnicos_desempeno": tecnicos_desempeno,
    })
