"""Estado de cuenta bancario (solo administrador): pantalla, PDF y Excel.
El cálculo está en app/utils/estado_cuenta_banco.py."""
from datetime import timedelta

from fastapi import APIRouter, Request, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.templates_env import templates, obtener_config_actual
from app.database import get_db
from app.deps import roles_required
from app.utils.estado_cuenta_banco import (
    estado_cuenta, periodo_desde_texto, excel_estado_cuenta, pdf_estado_cuenta, TIPOS,
)
from app.utils.turnos_caja import hoy_local

router = APIRouter()
BASE = "/banco/estado-cuenta"
solo_admin = roles_required("admin")


def _datos(db, desde, hasta, tipo):
    d, h = periodo_desde_texto(desde, hasta)
    return estado_cuenta(db, d, h, tipo if tipo in TIPOS or tipo == "entradas" else "")


def _nombre_archivo(ec, ext):
    return f"estado_cuenta_banco_{ec['desde'].strftime('%Y%m%d')}_{ec['hasta'].strftime('%Y%m%d')}.{ext}"


@router.get(BASE)
def banco_estado_cuenta(request: Request, desde: str = "", hasta: str = "", tipo: str = "",
                        db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    ec = _datos(db, desde, hasta, tipo)
    hoy = hoy_local()
    primero = hoy.replace(day=1)
    fin_anterior = primero - timedelta(days=1)
    return templates.TemplateResponse("banco/estado_cuenta.html", {
        "request": request, "usuario": usuario, "ec": ec,
        "desde": ec["desde"].isoformat(), "hasta": ec["hasta"].isoformat(), "hoy_iso": hoy.isoformat(),
        "este_mes": (primero.isoformat(), hoy.isoformat()),
        "mes_anterior": (fin_anterior.replace(day=1).isoformat(), fin_anterior.isoformat()),
    })


@router.get(BASE + "/excel")
def banco_estado_cuenta_excel(desde: str = "", hasta: str = "", tipo: str = "",
                              db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    ec = _datos(db, desde, hasta, tipo)
    cfg = obtener_config_actual()
    contenido = excel_estado_cuenta(ec, cfg.get("nombre_taller", "Mi Taller"), cfg.get("moneda", "L"))
    return Response(contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{_nombre_archivo(ec, "xlsx")}"'})


@router.get(BASE + "/pdf")
def banco_estado_cuenta_pdf(desde: str = "", hasta: str = "", tipo: str = "", descargar: int = 0,
                            db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    ec = _datos(db, desde, hasta, tipo)
    cfg = obtener_config_actual()
    contenido = pdf_estado_cuenta(ec, cfg.get("nombre_taller", "Mi Taller"), cfg.get("moneda", "L"))
    modo = "attachment" if descargar else "inline"
    return Response(contenido, media_type="application/pdf",
                    headers={"Content-Disposition": f'{modo}; filename="{_nombre_archivo(ec, "pdf")}"'})
