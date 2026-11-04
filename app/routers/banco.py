"""Estado de cuenta bancario (solo administrador): pantalla, PDF y Excel.
El cálculo está en app/utils/estado_cuenta_banco.py."""
from datetime import timedelta
from decimal import Decimal

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


def _banco(db, banco):
    from app.models import Banco
    try:
        b = db.get(Banco, int(banco))
    except (TypeError, ValueError):
        return None
    return b.id if b else None


def _datos(db, desde, hasta, tipo, banco=""):
    d, h = periodo_desde_texto(desde, hasta)
    return estado_cuenta(db, d, h, tipo if tipo in TIPOS or tipo == "entradas" else "", _banco(db, banco))


def _nombre_archivo(ec, ext):
    return f"estado_cuenta_banco_{ec['desde'].strftime('%Y%m%d')}_{ec['hasta'].strftime('%Y%m%d')}.{ext}"


@router.get(BASE)
def banco_estado_cuenta(request: Request, desde: str = "", hasta: str = "", tipo: str = "", banco: str = "",
                        db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    ec = _datos(db, desde, hasta, tipo, banco)
    hoy = hoy_local()
    primero = hoy.replace(day=1)
    fin_anterior = primero - timedelta(days=1)
    from datetime import datetime as _dt
    from app.utils.bancos import saldos_por_banco
    return templates.TemplateResponse("banco/estado_cuenta.html", {
        "request": request, "usuario": usuario, "ec": ec,
        "saldos_bancos": saldos_por_banco(db, _dt.utcnow() + timedelta(seconds=1)) if ec["varios_bancos"] else [],
        "desde": ec["desde"].isoformat(), "hasta": ec["hasta"].isoformat(), "hoy_iso": hoy.isoformat(),
        "este_mes": (primero.isoformat(), hoy.isoformat()),
        "mes_anterior": (fin_anterior.replace(day=1).isoformat(), fin_anterior.isoformat()),
    })


@router.get(BASE + "/excel")
def banco_estado_cuenta_excel(desde: str = "", hasta: str = "", tipo: str = "", banco: str = "",
                              db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    ec = _datos(db, desde, hasta, tipo, banco)
    cfg = obtener_config_actual()
    contenido = excel_estado_cuenta(ec, cfg.get("nombre_taller", "Mi Taller"), cfg.get("moneda", "L"))
    return Response(contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{_nombre_archivo(ec, "xlsx")}"'})


@router.get(BASE + "/pdf")
def banco_estado_cuenta_pdf(desde: str = "", hasta: str = "", tipo: str = "", banco: str = "", descargar: int = 0,
                            db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    ec = _datos(db, desde, hasta, tipo, banco)
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
def banco_cuadre(request: Request, fecha: str = "", real: str = "", banco: str = "", db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    from app.utils.cuadre_banco import saldo_sistema, pistas, cuadres, MOTIVOS_SALIDA, MOTIVOS_ENTRADA, q
    from app.utils.caja_calculos import calcular_liquidez
    from app.utils.bancos import bancos_activos, banco_principal, nombre_banco
    dia = _leer_dia(fecha)
    lista_bancos = bancos_activos(db)
    banco_id = _banco(db, banco) or banco_principal(db).id
    sistema = saldo_sistema(db, dia, banco_id)
    saldo_real = _leer_monto(real)
    diferencia = q(sistema - saldo_real) if saldo_real is not None else None
    panel = calcular_liquidez(db)["banco_actual"] if dia == hoy_local() and len(lista_bancos) == 1 else None
    return templates.TemplateResponse("banco/cuadre.html", {
        "request": request, "usuario": usuario, "dia": dia, "hoy_iso": hoy_local().isoformat(),
        "sistema": sistema, "real": saldo_real, "real_txt": real, "diferencia": diferencia, "panel": panel,
        "p": pistas(db, dia, diferencia, banco_id) if diferencia else None, "cuadres": cuadres(db),
        "bancos": lista_bancos, "banco_id": banco_id, "banco_nombre": nombre_banco(db, banco_id),
        "motivos_salida": MOTIVOS_SALIDA, "motivos_entrada": MOTIVOS_ENTRADA,
    })


@router.post(URL_CUADRE)
async def banco_cuadre_guardar(request: Request, db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    from fastapi.responses import RedirectResponse
    from urllib.parse import urlencode
    from app.utils.flash import flash
    from app.utils.cuadre_banco import cuadrar
    from app.utils.bancos import nombre_banco
    form = await request.form()
    dia = _leer_dia(form.get("fecha", ""))
    saldo_real = _leer_monto(form.get("real", ""))
    banco_id = _banco(db, form.get("banco", ""))
    volver = f"{URL_CUADRE}?" + urlencode({"fecha": dia.isoformat(), "real": form.get("real", ""), "banco": banco_id or ""})
    if saldo_real is None:
        flash(request, "Escribe el saldo real del banco.", "error")
        return RedirectResponse(volver, status_code=303)
    mov, diferencia, error = cuadrar(db, dia, saldo_real, form.get("motivo", ""), form.get("nota", ""), usuario["nombre_completo"], banco_id)
    if error:
        db.rollback()
        flash(request, error, "error")
        return RedirectResponse(volver, status_code=303)
    db.commit()
    flash(request, f"Banco cuadrado: se registró {'una salida' if diferencia > 0 else 'una entrada'} de L {abs(diferencia):,.2f} "
          f"({mov.categoria}). {nombre_banco(db, mov.banco_id)} al {dia.strftime('%d/%m/%Y')} queda en L {saldo_real:,.2f}.", "success")
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


# ---------------------------------------------------------------------------
# Bancos: agregar, editar y desactivar cuentas bancarias
# ---------------------------------------------------------------------------
URL_BANCOS = "/banco/cuentas"


@router.get(URL_BANCOS)
def bancos_lista(request: Request, db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    from datetime import datetime as _dt
    from app.utils.bancos import saldos_por_banco, todos_los_bancos
    saldos = {f["banco"].id: f["saldo"] for f in saldos_por_banco(db, _dt.utcnow() + timedelta(seconds=1))}
    bancos = todos_los_bancos(db)
    db.commit()  # por si se creó el banco principal
    return templates.TemplateResponse("banco/cuentas.html", {
        "request": request, "usuario": usuario, "bancos": bancos, "saldos": saldos, "hoy_iso": hoy_local().isoformat(),
    })


@router.post(URL_BANCOS)
async def bancos_crear(request: Request, db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    from datetime import datetime as _dt
    from fastapi.responses import RedirectResponse
    from app.utils.flash import flash
    from app.models import Banco, MovimientoFinanciero, CATEGORIA_SALDO_INICIAL_BANCO
    from app.utils.turnos_caja import inicio_dia_local_en_utc
    form = await request.form()
    nombre = (form.get("nombre") or "").strip()[:100]
    if not nombre:
        flash(request, "Escribe el nombre del banco.", "error")
        return RedirectResponse(URL_BANCOS, status_code=303)
    if db.query(Banco).filter(Banco.nombre.ilike(nombre), Banco.numero_cuenta == (form.get("numero_cuenta") or "").strip()).first():
        flash(request, "Ese banco con ese número de cuenta ya existe.", "error")
        return RedirectResponse(URL_BANCOS, status_code=303)
    saldo = _leer_monto(form.get("saldo_inicial", "")) or Decimal("0")
    banco = Banco(nombre=nombre, numero_cuenta=(form.get("numero_cuenta") or "").strip()[:60],
                  tipo_cuenta=(form.get("tipo_cuenta") or "").strip()[:40], activo=True, principal=False)
    db.add(banco)
    db.flush()
    if saldo > 0:
        dia = _leer_dia(form.get("fecha_saldo", ""))
        db.add(MovimientoFinanciero(
            tipo="ingreso", categoria=CATEGORIA_SALDO_INICIAL_BANCO, monto=saldo.quantize(Decimal("0.01")),
            fecha=min(_dt.utcnow(), inicio_dia_local_en_utc(dia)), descripcion=f"Saldo con que empezó {nombre} en el sistema",
            usuario_nombre=usuario["nombre_completo"], referencia="Saldo inicial", cuenta="banco", banco_id=banco.id,
        ))
    db.commit()
    flash(request, f"Banco «{nombre}» agregado" + (f" con saldo inicial de L {saldo:,.2f}." if saldo > 0 else ".")
          + " Ya se puede elegir al cobrar o pagar por transferencia o tarjeta.", "success")
    return RedirectResponse(URL_BANCOS, status_code=303)


@router.post(URL_BANCOS + "/{banco_id}/editar")
async def bancos_editar(banco_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    from fastapi.responses import RedirectResponse
    from app.utils.flash import flash
    from app.models import Banco
    form = await request.form()
    banco = db.get(Banco, banco_id)
    nombre = (form.get("nombre") or "").strip()[:100]
    if banco and nombre:
        banco.nombre = nombre
        banco.numero_cuenta = (form.get("numero_cuenta") or "").strip()[:60]
        banco.tipo_cuenta = (form.get("tipo_cuenta") or "").strip()[:40]
        db.commit()
        flash(request, f"Banco «{nombre}» actualizado.", "success")
    return RedirectResponse(URL_BANCOS, status_code=303)


@router.post(URL_BANCOS + "/{banco_id}/estado")
def bancos_estado(banco_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(solo_admin)):
    from fastapi.responses import RedirectResponse
    from app.utils.flash import flash
    from app.models import Banco
    banco = db.get(Banco, banco_id)
    if banco and not banco.principal:
        banco.activo = not banco.activo
        db.commit()
        flash(request, f"«{banco.nombre}» " + ("vuelve a aparecer para elegir." if banco.activo else
              "ya no aparece para elegir (sus movimientos y saldo se conservan)."), "success")
    elif banco:
        flash(request, "El banco principal no se puede desactivar.", "error")
    return RedirectResponse(URL_BANCOS, status_code=303)
