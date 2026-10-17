"""Apertura y cierre de caja: abrir, cerrar (arqueo), historial con
búsqueda por fecha, detalle de cada turno, edición y reapertura.

Permisos:
  * Abrir y cerrar: Cajera (rol vendedor) y Administrador.
  * Editar una caja ABIERTA: Cajera y Administrador.
  * Editar una caja CERRADA y reabrirla: solo el Administrador.
  * Programar/activar/desactivar el bloqueo: solo el Administrador.
Las reglas y el cálculo del arqueo están en app/utils/turnos_caja.py.
"""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.templates_env import templates
from app.database import get_db
from app.deps import roles_required
from app.models import Configuracion, TurnoCaja, TurnoCajaEvento, TURNO_ABIERTO, TURNO_CERRADO
from app.utils.flash import flash
from app.utils.calculations import to_decimal
from app.utils.turnos_caja import (
    turno_abierto, calcular_resumen_turno, caja_obligatoria_activa, es_turno_de_dia_anterior,
    fecha_local, hoy_local, a_hora_local, inicio_dia_local_en_utc, local_a_utc,
    ultimo_efectivo_contado, resumen_por_dia,
)

router = APIRouter()

URL_TURNOS = "/caja/turnos"


def _url_detalle(turno_id: int) -> str:
    return f"{URL_TURNOS}/{turno_id}"


def _monto(valor: str, nombre: str) -> Decimal:
    try:
        monto = to_decimal((valor or "").strip() or "0")
    except (InvalidOperation, ValueError):
        raise ValueError(f"{nombre}: escribe un número válido.")
    if monto < 0:
        raise ValueError(f"{nombre}: no puede ser negativo.")
    return monto.quantize(Decimal("0.01"))


def _parse_fecha(valor: str):
    try:
        return datetime.strptime((valor or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _evento(db: Session, turno: TurnoCaja, accion: str, usuario: dict, detalle: str = "") -> None:
    db.add(TurnoCajaEvento(
        turno_id=turno.id, accion=accion, usuario_nombre=usuario["nombre_completo"],
        detalle=detalle.strip(), fecha=datetime.utcnow(),
    ))


def _recalcular_arqueo(db: Session, turno: TurnoCaja) -> None:
    resumen = calcular_resumen_turno(db, turno)
    turno.efectivo_esperado = resumen["efectivo_esperado"]
    if turno.efectivo_contado is not None:
        turno.diferencia = (to_decimal(turno.efectivo_contado) - resumen["efectivo_esperado"]).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Pantalla principal: estado actual + abrir/cerrar + historial
# ---------------------------------------------------------------------------
@router.get(URL_TURNOS)
def turnos_index(
    request: Request, desde: str = "", hasta: str = "", estado: str = "",
    db: Session = Depends(get_db), usuario=Depends(roles_required("vendedor")),
):
    actual = turno_abierto(db)
    resumen_actual = calcular_resumen_turno(db, actual) if actual else None
    # Primero lo del día: con la caja abierta, siempre se muestra "hoy"
    # aunque todavía no tenga movimientos.
    dias_actual = resumen_por_dia(resumen_actual, incluir_dia=hoy_local()) if actual else []

    query = db.query(TurnoCaja)
    fecha_desde = _parse_fecha(desde)
    fecha_hasta = _parse_fecha(hasta)
    if fecha_desde:
        query = query.filter(TurnoCaja.fecha_apertura >= inicio_dia_local_en_utc(fecha_desde))
    if fecha_hasta:
        query = query.filter(TurnoCaja.fecha_apertura < inicio_dia_local_en_utc(fecha_hasta + timedelta(days=1)))
    if estado in (TURNO_ABIERTO, TURNO_CERRADO):
        query = query.filter(TurnoCaja.estado == estado)
    hay_filtro = bool(fecha_desde or fecha_hasta or estado)
    historial = query.order_by(TurnoCaja.fecha_apertura.desc()).limit(500 if hay_filtro else 60).all()

    cfg = db.get(Configuracion, 1)
    return templates.TemplateResponse("caja/turnos.html", {
        "request": request, "usuario": usuario,
        "actual": actual, "resumen_actual": resumen_actual, "dias_actual": dias_actual,
        "actual_de_dia_anterior": bool(actual and es_turno_de_dia_anterior(actual)),
        "historial": historial, "hay_filtro": hay_filtro,
        "desde": desde, "hasta": hasta, "estado": estado,
        "hoy_iso": hoy_local().isoformat(),
        "sugerido_inicial": ultimo_efectivo_contado(db),
        "obligatoria_activa": caja_obligatoria_activa(db),
        "obligatoria_desde": a_hora_local(cfg.caja_obligatoria_desde) if cfg and cfg.caja_obligatoria_desde else None,
        "a_hora_local": a_hora_local,
    })


@router.post(f"{URL_TURNOS}/abrir")
def turnos_abrir(
    request: Request, monto_inicial: str = Form("0"), notas_apertura: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(roles_required("vendedor")),
):
    actual = turno_abierto(db)
    if actual:
        if es_turno_de_dia_anterior(actual):
            flash(request, "Primero cierra la caja que quedó abierta del día anterior.", "error")
        else:
            flash(request, "Ya hay una caja abierta.", "error")
        return RedirectResponse(URL_TURNOS, status_code=303)
    try:
        monto = _monto(monto_inicial, "Efectivo inicial")
    except ValueError as e:
        flash(request, str(e), "error")
        return RedirectResponse(URL_TURNOS, status_code=303)

    turno = TurnoCaja(
        estado=TURNO_ABIERTO, fecha_apertura=datetime.utcnow(),
        abierta_por=usuario["nombre_completo"], monto_inicial=monto,
        notas_apertura=notas_apertura.strip(),
    )
    db.add(turno)
    db.flush()
    _evento(db, turno, "apertura", usuario, f"Efectivo inicial: L {monto:,.2f}")
    db.commit()
    flash(request, f"Caja abierta con L {monto:,.2f} de efectivo inicial.", "success")
    return RedirectResponse(URL_TURNOS, status_code=303)


@router.post(URL_TURNOS + "/{turno_id}/cerrar")
def turnos_cerrar(
    turno_id: int, request: Request,
    efectivo_contado: str = Form(...), notas_cierre: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(roles_required("vendedor")),
):
    turno = db.get(TurnoCaja, turno_id)
    if not turno or turno.estado != TURNO_ABIERTO:
        flash(request, "Esa caja no está abierta.", "error")
        return RedirectResponse(URL_TURNOS, status_code=303)
    if not (efectivo_contado or "").strip():
        flash(request, "Escribe el efectivo que contaste en la caja para poder cerrarla.", "error")
        return RedirectResponse(URL_TURNOS, status_code=303)
    try:
        contado = _monto(efectivo_contado, "Efectivo contado")
    except ValueError as e:
        flash(request, str(e), "error")
        return RedirectResponse(URL_TURNOS, status_code=303)

    resumen = calcular_resumen_turno(db, turno)
    turno.estado = TURNO_CERRADO
    turno.fecha_cierre = datetime.utcnow()
    turno.cerrada_por = usuario["nombre_completo"]
    turno.efectivo_esperado = resumen["efectivo_esperado"]
    turno.efectivo_contado = contado
    turno.diferencia = (contado - resumen["efectivo_esperado"]).quantize(Decimal("0.01"))
    turno.notas_cierre = notas_cierre.strip()
    turno.cerrada_tarde = es_turno_de_dia_anterior(turno)
    _evento(
        db, turno, "cierre", usuario,
        f"Esperado: L {turno.efectivo_esperado:,.2f} · Contado: L {contado:,.2f} · "
        f"Diferencia: L {turno.diferencia:,.2f}" + (" · Cerrada otro día (se olvidó cerrar)" if turno.cerrada_tarde else ""),
    )
    db.commit()

    if turno.diferencia == 0:
        flash(request, "Caja cerrada. El efectivo cuadra exactamente.", "success")
    elif turno.diferencia > 0:
        flash(request, f"Caja cerrada con un SOBRANTE de L {turno.diferencia:,.2f}.", "success")
    else:
        flash(request, f"Caja cerrada con un FALTANTE de L {abs(turno.diferencia):,.2f}.", "error")
    return RedirectResponse(_url_detalle(turno.id), status_code=303)


# ---------------------------------------------------------------------------
# Detalle, edición y reapertura
# ---------------------------------------------------------------------------
@router.get(URL_TURNOS + "/{turno_id}")
def turnos_detalle(
    turno_id: int, request: Request,
    db: Session = Depends(get_db), usuario=Depends(roles_required("vendedor")),
):
    turno = db.get(TurnoCaja, turno_id)
    if not turno:
        flash(request, "Apertura de caja no encontrada.", "error")
        return RedirectResponse(URL_TURNOS, status_code=303)
    es_admin = usuario.get("rol") == "admin"
    abierta = turno.estado == TURNO_ABIERTO
    resumen = calcular_resumen_turno(db, turno)
    return templates.TemplateResponse("caja/turno_detalle.html", {
        "request": request, "usuario": usuario, "turno": turno,
        "resumen": resumen,
        "dias": resumen_por_dia(resumen, incluir_dia=hoy_local() if abierta else None),
        "abierta": abierta,
        "puede_editar": abierta or es_admin,
        "puede_reabrir": es_admin and not abierta and turno_abierto(db) is None,
        "hay_otra_abierta": (not abierta) and turno_abierto(db) is not None,
        "es_admin": es_admin,
        "a_hora_local": a_hora_local,
        "fecha_apertura_local": fecha_local(turno.fecha_apertura),
    })


@router.post(URL_TURNOS + "/{turno_id}/editar")
def turnos_editar(
    turno_id: int, request: Request,
    monto_inicial: str = Form(""), notas_apertura: str = Form(""),
    efectivo_contado: str = Form(""), notas_cierre: str = Form(""),
    motivo: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(roles_required("vendedor")),
):
    turno = db.get(TurnoCaja, turno_id)
    if not turno:
        flash(request, "Apertura de caja no encontrada.", "error")
        return RedirectResponse(URL_TURNOS, status_code=303)
    es_admin = usuario.get("rol") == "admin"
    cerrada = turno.estado != TURNO_ABIERTO
    if cerrada and not es_admin:
        flash(request, "Solo el administrador puede editar una caja que ya fue cerrada.", "error")
        return RedirectResponse(_url_detalle(turno.id), status_code=303)
    if cerrada and not motivo.strip():
        flash(request, "Escribe el motivo de la corrección (queda registrado en el historial).", "error")
        return RedirectResponse(_url_detalle(turno.id), status_code=303)

    try:
        nuevo_inicial = _monto(monto_inicial, "Efectivo inicial")
        nuevo_contado = _monto(efectivo_contado, "Efectivo contado") if cerrada else None
    except ValueError as e:
        flash(request, str(e), "error")
        return RedirectResponse(_url_detalle(turno.id), status_code=303)

    cambios = []
    if nuevo_inicial != to_decimal(turno.monto_inicial or 0):
        cambios.append(f"Efectivo inicial: L {to_decimal(turno.monto_inicial or 0):,.2f} → L {nuevo_inicial:,.2f}")
        turno.monto_inicial = nuevo_inicial
    if notas_apertura.strip() != (turno.notas_apertura or "").strip():
        cambios.append("Notas de apertura modificadas")
        turno.notas_apertura = notas_apertura.strip()
    if cerrada:
        anterior_contado = to_decimal(turno.efectivo_contado or 0)
        if nuevo_contado != anterior_contado:
            cambios.append(f"Efectivo contado: L {anterior_contado:,.2f} → L {nuevo_contado:,.2f}")
            turno.efectivo_contado = nuevo_contado
        if notas_cierre.strip() != (turno.notas_cierre or "").strip():
            cambios.append("Notas de cierre modificadas")
            turno.notas_cierre = notas_cierre.strip()

    if not cambios:
        flash(request, "No había cambios que guardar.", "success")
        return RedirectResponse(_url_detalle(turno.id), status_code=303)

    if cerrada:
        diferencia_anterior = to_decimal(turno.diferencia or 0)
        _recalcular_arqueo(db, turno)
        if to_decimal(turno.diferencia or 0) != diferencia_anterior:
            cambios.append(f"Diferencia: L {diferencia_anterior:,.2f} → L {to_decimal(turno.diferencia):,.2f}")
    detalle = "; ".join(cambios) + (f". Motivo: {motivo.strip()}" if motivo.strip() else "")
    _evento(db, turno, "edicion", usuario, detalle)
    db.commit()
    flash(request, "Cambios guardados.", "success")
    return RedirectResponse(_url_detalle(turno.id), status_code=303)


@router.post(URL_TURNOS + "/{turno_id}/reabrir")
def turnos_reabrir(
    turno_id: int, request: Request, motivo: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    turno = db.get(TurnoCaja, turno_id)
    if not turno or turno.estado == TURNO_ABIERTO:
        flash(request, "Esa caja no está cerrada.", "error")
        return RedirectResponse(URL_TURNOS, status_code=303)
    if turno_abierto(db) is not None:
        flash(request, "Ya hay otra caja abierta. Ciérrala primero para poder reabrir esta.", "error")
        return RedirectResponse(_url_detalle(turno.id), status_code=303)
    if not motivo.strip():
        flash(request, "Escribe el motivo de la reapertura (queda registrado en el historial).", "error")
        return RedirectResponse(_url_detalle(turno.id), status_code=303)

    cierre_anterior = (
        f"Cierre anterior: {a_hora_local(turno.fecha_cierre).strftime('%d/%m/%Y %I:%M %p') if turno.fecha_cierre else '-'}"
        f" por {turno.cerrada_por or '-'} · Esperado L {to_decimal(turno.efectivo_esperado or 0):,.2f}"
        f" · Contado L {to_decimal(turno.efectivo_contado or 0):,.2f}"
        f" · Diferencia L {to_decimal(turno.diferencia or 0):,.2f}"
    )
    turno.estado = TURNO_ABIERTO
    turno.fecha_cierre = None
    turno.cerrada_por = None
    turno.efectivo_esperado = None
    turno.efectivo_contado = None
    turno.diferencia = None
    turno.cerrada_tarde = False
    _evento(db, turno, "reapertura", usuario, f"Motivo: {motivo.strip()}. {cierre_anterior}")
    db.commit()
    flash(request, "Caja reabierta. Cuando termine, la cajera debe cerrarla de nuevo con su conteo.", "success")
    return RedirectResponse(_url_detalle(turno.id), status_code=303)


# ---------------------------------------------------------------------------
# Configuración del bloqueo (solo admin)
# ---------------------------------------------------------------------------
@router.post(f"{URL_TURNOS}/configuracion")
def turnos_configuracion(
    request: Request, accion: str = Form(...), fecha_hora: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    cfg = db.get(Configuracion, 1)
    if not cfg:
        flash(request, "No se encontró la configuración del taller.", "error")
        return RedirectResponse(URL_TURNOS, status_code=303)
    if accion == "activar_ahora":
        cfg.caja_obligatoria_desde = datetime.utcnow()
        mensaje = "Listo: desde ahora es obligatorio abrir caja para cobrar, abonar, facturar y vender."
    elif accion == "desactivar":
        cfg.caja_obligatoria_desde = None
        mensaje = "Bloqueo desactivado: se puede cobrar, abonar, facturar y vender sin caja abierta."
    elif accion == "programar":
        try:
            local = datetime.strptime(fecha_hora.strip(), "%Y-%m-%dT%H:%M")
        except ValueError:
            flash(request, "Elige una fecha y hora válidas.", "error")
            return RedirectResponse(URL_TURNOS, status_code=303)
        cfg.caja_obligatoria_desde = local_a_utc(local)
        mensaje = f"Listo: será obligatorio abrir caja a partir del {local.strftime('%d/%m/%Y %I:%M %p')}."
    else:
        return RedirectResponse(URL_TURNOS, status_code=303)
    db.commit()
    flash(request, mensaje, "success")
    return RedirectResponse(URL_TURNOS, status_code=303)
