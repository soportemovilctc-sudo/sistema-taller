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


# ---------------------------------------------------------------------------
# Cuadre con el saldo real del banco
# ---------------------------------------------------------------------------
URL_CUADRE = "/banco/cuadre"


def _leer_dia(texto: str):
    from datetime import datetime as _dt
    try:
        d = _dt.strptime((texto or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return hoy_local()
    return min(d, hoy_local())


def _leer_monto(texto: str):
    from app.utils.calculations import to_decimal
    t = (texto or "").strip().replace(",", "").replace("L", "").strip()
    if not t:
        return None
    try:
        return to_decimal(t)
    except Exception:  # noqa: BLE001
        return None


@router.get(URL_CUADRE)
def banco_cuadre(request: Request, fecha: str = "", real: str = "", db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    from app.utils.cuadre_banco import saldo_sistema, pistas, cuadres, MOTIVOS_SALIDA, MOTIVOS_ENTRADA, q
    from app.utils.caja_calculos import calcular_liquidez
    dia = _leer_dia(fecha)
    sistema = saldo_sistema(db, dia)
    saldo_real = _leer_monto(real)
    diferencia = q(sistema - saldo_real) if saldo_real is not None else None
    panel = calcular_liquidez(db)["banco_actual"] if dia == hoy_local() else None
    return templates.TemplateResponse("banco/cuadre.html", {
        "request": request, "usuario": usuario, "dia": dia, "hoy_iso": hoy_local().isoformat(),
        "sistema": sistema, "real": saldo_real, "real_txt": real, "diferencia": diferencia, "panel": panel,
        "p": pistas(db, dia, diferencia) if diferencia else None, "cuadres": cuadres(db),
        "motivos_salida": MOTIVOS_SALIDA, "motivos_entrada": MOTIVOS_ENTRADA,
    })


@router.post(URL_CUADRE)
async def banco_cuadre_guardar(request: Request, db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    from fastapi.responses import RedirectResponse
    from urllib.parse import urlencode
    from app.utils.flash import flash
    from app.utils.cuadre_banco import cuadrar
    form = await request.form()
    dia = _leer_dia(form.get("fecha", ""))
    saldo_real = _leer_monto(form.get("real", ""))
    volver = f"{URL_CUADRE}?" + urlencode({"fecha": dia.isoformat(), "real": form.get("real", "")})
    if saldo_real is None:
        flash(request, "Escribe el saldo real del banco.", "error")
        return RedirectResponse(volver, status_code=303)
    mov, diferencia, error = cuadrar(db, dia, saldo_real, form.get("motivo", ""), form.get("nota", ""), usuario["nombre_completo"])
    if error:
        db.rollback()
        flash(request, error, "error")
        return RedirectResponse(volver, status_code=303)
    db.commit()
    flash(request, f"Banco cuadrado: se registró {'una salida' if diferencia > 0 else 'una entrada'} de L {abs(diferencia):,.2f} "
          f"({mov.categoria}). El banco del sistema al {dia.strftime('%d/%m/%Y')} queda en L {saldo_real:,.2f}.", "success")
    return RedirectResponse(volver, status_code=303)


@router.post(URL_CUADRE + "/{mov_id}/deshacer")
def banco_cuadre_deshacer(mov_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    from fastapi.responses import RedirectResponse
    from app.utils.flash import flash
    from app.models import MovimientoFinanciero
    from app.utils.cuadre_banco import deshacer
    error = deshacer(db, db.get(MovimientoFinanciero, mov_id), usuario["nombre_completo"])
    if error:
        flash(request, error, "error")
    else:
        db.commit()
        flash(request, "Cuadre anulado: ya no cuenta en el banco ni en la contabilidad.", "success")
    return RedirectResponse(URL_CUADRE, status_code=303)
