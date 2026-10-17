"""Revisión del sistema (solo administrador).

GET /revision muestra lo que no cuadra (ver app/utils/revision_sistema.py).
Cada botón corrige UN caso concreto, después de que el administrador lo
confirma, y deja constancia (bitácora de la caja o flash). Nada se borra:
  * Quitar un registro de una caja: solo se desvincula del cierre de esa
    caja (turno_caja_id = NULL); sigue en Contabilidad, Caja Chica, etc.
  * Efectivo inicial / recalcular: igual que una corrección del admin en el
    detalle de la caja, con su motivo en la bitácora.
  * Factura anulada: sus ingresos se excluyen (igual que al anular).
  * Factura sin ingreso: se crea con la fecha original de la factura.
  * Orden: se recalculan total, abonado y saldo con sus propios datos.
"""
from decimal import Decimal

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.templates_env import templates
from app.database import get_db
from app.deps import roles_required
from app.models import TurnoCaja, MovimientoFinanciero, Factura, OrdenServicio, TURNO_ABIERTO
from app.utils.flash import flash
from app.utils.calculations import to_decimal, recalcular_orden
from app.utils.libro_diario import eliminar_asiento_de_movimiento
from app.utils.revision_sistema import revisar_sistema
from app.routers.turnos_caja import _evento, _recalcular_arqueo, _monto

router = APIRouter()
URL = "/revision"


def _volver(ancla: str = "") -> RedirectResponse:
    return RedirectResponse(URL + (f"#{ancla}" if ancla else ""), status_code=303)


def _l(v) -> str:
    return f"L {to_decimal(v or 0):,.2f}"


@router.get(URL)
def revision_index(request: Request, db: Session = Depends(get_db), usuario=Depends(roles_required("admin"))):
    return templates.TemplateResponse("revision/index.html", {
        "request": request, "usuario": usuario, "rev": revisar_sistema(db),
    })


# ---------------------------------------------------------------------------
# Cajas
# ---------------------------------------------------------------------------
@router.post(URL + "/caja/{turno_id}/quitar/mov/{mov_id}")
def revision_quitar_mov(
    turno_id: int, mov_id: int, request: Request, motivo: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    turno = db.get(TurnoCaja, turno_id)
    mov = db.get(MovimientoFinanciero, mov_id)
    if not turno or not mov or mov.turno_caja_id != turno.id:
        flash(request, "Ese registro ya no está en esa caja.", "error")
        return _volver()
    if not motivo.strip():
        flash(request, "Escribe el motivo (queda en la bitácora de la caja).", "error")
        return _volver(f"caja-{turno.id}")
    esperado_antes = to_decimal(turno.efectivo_esperado or 0)
    mov.turno_caja_id = None
    db.flush()
    if turno.estado != TURNO_ABIERTO:
        _recalcular_arqueo(db, turno)
    tipo = "Ingreso" if mov.tipo == "ingreso" else "Salida"
    detalle = f"Se quitó del cierre: {tipo} #{mov.id} · {mov.categoria} · {_l(mov.monto)}"
    if turno.estado != TURNO_ABIERTO:
        detalle += f". Esperado: {_l(esperado_antes)} → {_l(turno.efectivo_esperado)}"
    _evento(db, turno, "edicion", usuario, f"{detalle}. Motivo: {motivo.strip()}")
    db.commit()
    flash(request, f"Listo: ese registro ya no cuenta en el cierre de la caja #{turno.id} (sigue en la contabilidad).", "success")
    return _volver(f"caja-{turno.id}")


@router.post(URL + "/caja/{turno_id}/recalcular")
def revision_recalcular_caja(
    turno_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    turno = db.get(TurnoCaja, turno_id)
    if not turno:
        flash(request, "Caja no encontrada.", "error")
        return _volver()
    antes_e, antes_d = to_decimal(turno.efectivo_esperado or 0), to_decimal(turno.diferencia or 0)
    _recalcular_arqueo(db, turno)
    _evento(db, turno, "edicion", usuario,
            f"Cierre recalculado desde Revisión del sistema. Esperado: {_l(antes_e)} → {_l(turno.efectivo_esperado)}; "
            f"diferencia: {_l(antes_d)} → {_l(turno.diferencia)}")
    db.commit()
    flash(request, f"Caja #{turno.id} recalculada.", "success")
    return _volver(f"caja-{turno.id}")


@router.post(URL + "/caja/{turno_id}/efectivo-inicial")
def revision_efectivo_inicial(
    turno_id: int, request: Request, valor: str = Form(""), motivo: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    turno = db.get(TurnoCaja, turno_id)
    if not turno:
        flash(request, "Caja no encontrada.", "error")
        return _volver()
    if not motivo.strip():
        flash(request, "Escribe el motivo (queda en la bitácora de la caja).", "error")
        return _volver(f"caja-{turno.id}")
    try:
        nuevo = _monto(valor, "Efectivo inicial")
    except ValueError as e:
        flash(request, str(e), "error")
        return _volver(f"caja-{turno.id}")
    antes = to_decimal(turno.monto_inicial or 0)
    turno.monto_inicial = nuevo
    db.flush()
    _recalcular_arqueo(db, turno)
    _evento(db, turno, "edicion", usuario,
            f"Efectivo inicial: {_l(antes)} → {_l(nuevo)} (desde Revisión del sistema). "
            f"Esperado: {_l(turno.efectivo_esperado)}; diferencia: {_l(turno.diferencia)}. Motivo: {motivo.strip()}")
    db.commit()
    flash(request, f"Caja #{turno.id}: efectivo inicial cambiado a {_l(nuevo)}.", "success")
    return _volver(f"caja-{turno.id}")


# ---------------------------------------------------------------------------
# Facturas
# ---------------------------------------------------------------------------
@router.post(URL + "/factura/{factura_id}/excluir-ingresos")
def revision_excluir_ingresos(
    factura_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    factura = db.get(Factura, factura_id)
    if not factura or not factura.anulada:
        flash(request, "Solo se excluyen los ingresos de una factura anulada.", "error")
        return _volver("dinero")
    movs = db.query(MovimientoFinanciero).filter(
        MovimientoFinanciero.factura_id == factura.id, MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ).all()
    for mov in movs:
        mov.excluir_de_contabilidad = True
        eliminar_asiento_de_movimiento(db, mov.id)
    db.commit()
    flash(request, f"Factura {factura.numero_documento}: {len(movs)} ingreso(s) dejaron de contar (no se borraron).", "success")
    return _volver("dinero")


@router.post(URL + "/factura/{factura_id}/crear-ingreso")
def revision_crear_ingreso(
    factura_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    from app.routers.facturacion import _crear_ingresos_factura

    factura = db.get(Factura, factura_id)
    orden = db.get(OrdenServicio, factura.orden_id) if factura and factura.orden_id else None
    if not factura or factura.anulada or not orden:
        flash(request, "Esa factura no aplica (anulada o sin orden).", "error")
        return _volver("dinero")
    ya = db.query(MovimientoFinanciero).filter(
        MovimientoFinanciero.factura_id == factura.id, MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ).count()
    if ya:
        flash(request, f"La factura {factura.numero_documento} ya tiene su ingreso.", "success")
        return _volver("dinero")
    total = to_decimal(factura.total)
    isv = to_decimal(factura.isv_monto or 0)
    # Se marca con la caja de la factura (no con la que esté abierta hoy).
    # Igual no suma en el arqueo: el efectivo se contó con el abono.
    _crear_ingresos_factura(db, factura, orden, usuario["nombre_completo"],
                            monto_neto_total=(total - isv).quantize(Decimal("0.01")), isv_monto_total=isv)
    for mov in db.query(MovimientoFinanciero).filter(MovimientoFinanciero.factura_id == factura.id).all():
        mov.turno_caja_id = factura.turno_caja_id
    db.commit()
    flash(request, f"Ingreso de la factura {factura.numero_documento} registrado con su fecha original.", "success")
    return _volver("dinero")


# ---------------------------------------------------------------------------
# Órdenes
# ---------------------------------------------------------------------------
@router.post(URL + "/orden/{orden_id}/recalcular")
def revision_recalcular_orden(
    orden_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        flash(request, "Orden no encontrada.", "error")
        return _volver("ordenes")
    antes = (to_decimal(orden.total or 0), to_decimal(orden.abonado or 0), to_decimal(orden.saldo or 0))
    recalcular_orden(orden)
    db.commit()
    flash(request, f"Orden {orden.numero_orden}: total {_l(antes[0])} → {_l(orden.total)}, abonado {_l(antes[1])} → "
                   f"{_l(orden.abonado)}, saldo {_l(antes[2])} → {_l(orden.saldo)}.", "success")
    return _volver("ordenes")
