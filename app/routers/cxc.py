"""CxC: cuentas por cobrar anotadas a mano (ventas al crédito y préstamos).
La lógica de dinero está en app/utils/cxc.py."""
from datetime import datetime, date

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.templates_env import templates
from app.database import get_db
from app.models import (
    Cliente, CuentaPorCobrar, CxCPago, ConfiguracionFacturacion,
    CXC_VENTA, CXC_PRESTAMO, CXC_PENDIENTE, CXC_PAGADA, CXC_ANULADA,
)
from app.utils.flash import flash
from app.utils.calculations import to_decimal
from app.utils.turnos_caja import verificar_caja, hoy_local, a_hora_local
from app.utils.bancos import nombre_banco
from app.utils import cxc as C
from app.utils.pago_mixto import FORMA_MIXTO, leer_partes, total as total_partes, texto as texto_partes
from app.deps import roles_required

router = APIRouter()
caja_o_admin = roles_required("vendedor")  # admin y cajera


def _tasa_isv(db: Session):
    cfg = db.get(ConfiguracionFacturacion, 1)
    return to_decimal(cfg.isv_tasa if cfg and cfg.isv_tasa is not None else 15)


def _fecha(txt: str):
    try:
        return datetime.strptime((txt or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


@router.get("/cxc")
def cxc_lista(request: Request, ver: str = "pendientes", tipo: str = "", q: str = "",
              db: Session = Depends(get_db), usuario=Depends(caja_o_admin)):
    hoy = hoy_local()
    base = db.query(CuentaPorCobrar)
    if tipo in (CXC_VENTA, CXC_PRESTAMO):
        base = base.filter(CuentaPorCobrar.tipo == tipo)
    if q.strip():
        like = f"%{q.strip()}%"
        base = base.filter(or_(CuentaPorCobrar.deudor.ilike(like), CuentaPorCobrar.numero.ilike(like),
                               CuentaPorCobrar.concepto.ilike(like), CuentaPorCobrar.telefono.ilike(like)))
    todas = base.order_by(CuentaPorCobrar.fecha.desc()).all()
    pendientes = [c for c in todas if c.estado == CXC_PENDIENTE]
    vencidas = [c for c in pendientes if c.vence and c.vence < hoy]
    grupos = {"pendientes": pendientes, "vencidas": vencidas,
              "pagadas": [c for c in todas if c.estado == CXC_PAGADA],
              "anuladas": [c for c in todas if c.estado == CXC_ANULADA]}
    if ver not in grupos:
        ver = "pendientes"
    filas = grupos[ver]
    if ver in ("pendientes", "vencidas"):
        filas = sorted(filas, key=lambda c: (c.vence or date.max, c.fecha))
    resumen = {
        "por_cobrar": sum((c.saldo for c in pendientes), C.CERO),
        "ventas": sum((c.saldo for c in pendientes if c.tipo == CXC_VENTA), C.CERO),
        "prestamos": sum((c.saldo for c in pendientes if c.tipo == CXC_PRESTAMO), C.CERO),
        "vencido": sum((c.saldo for c in vencidas), C.CERO),
    }
    return templates.TemplateResponse("cxc/lista.html", {
        "request": request, "usuario": usuario, "filas": filas, "ver": ver, "tipo": tipo, "q": q, "hoy": hoy,
        "n": {k: len(v) for k, v in grupos.items()}, "resumen": resumen,
    })


@router.get("/cxc/nueva")
def cxc_nueva(request: Request, tipo: str = CXC_VENTA, db: Session = Depends(get_db), usuario=Depends(caja_o_admin)):
    if tipo not in (CXC_VENTA, CXC_PRESTAMO):
        tipo = CXC_VENTA
    clientes = db.query(Cliente).order_by(Cliente.nombre).all()
    return templates.TemplateResponse("cxc/nueva.html", {
        "request": request, "usuario": usuario, "tipo": tipo, "clientes": clientes, "tasa_isv": _tasa_isv(db),
        "hoy_iso": hoy_local().isoformat(),
    })


@router.post("/cxc/nueva")
def cxc_crear(request: Request, tipo: str = Form(CXC_VENTA), cliente_id: str = Form(""), deudor: str = Form(""),
              telefono: str = Form(""), concepto: str = Form(""), monto: str = Form(""), con_isv: str = Form(""),
              vence: str = Form(""), cuenta_salida: str = Form("caja_chica"), banco_id: str = Form(""),
              db: Session = Depends(get_db), usuario=Depends(caja_o_admin)):
    volver = f"/cxc/nueva?tipo={tipo}"
    cliente = db.get(Cliente, int(cliente_id)) if cliente_id.strip().isdigit() else None
    if cliente:
        deudor = deudor.strip() or cliente.nombre
        telefono = telefono.strip() or (cliente.whatsapp or cliente.telefono or "")
    if tipo == CXC_PRESTAMO and cuenta_salida != "banco":
        mensaje_caja = verificar_caja(db)
        if mensaje_caja:
            flash(request, f"No se anotó el préstamo: sale efectivo de la caja. {mensaje_caja}", "error")
            return RedirectResponse(volver, status_code=303)
    try:
        cxc = C.crear(db, tipo=tipo, deudor=deudor, cliente_id=cliente.id if cliente else None, telefono=telefono,
                      concepto=concepto, monto=monto, con_isv=con_isv == "1", tasa_isv=_tasa_isv(db), vence=_fecha(vence),
                      cuenta_salida=cuenta_salida, banco_id_raw=banco_id, usuario_nombre=usuario["nombre_completo"])
    except ValueError as e:
        db.rollback()
        flash(request, str(e), "error")
        return RedirectResponse(volver, status_code=303)
    db.commit()
    if tipo == CXC_PRESTAMO:
        origen = "la Caja Chica" if cxc.cuenta_salida == "caja_chica" else nombre_banco(db, cxc.banco_id)
        flash(request, f"Préstamo {cxc.numero} anotado: salieron L {cxc.monto:,.2f} de {origen}.", "success")
    else:
        flash(request, f"Venta al crédito {cxc.numero} anotada por L {cxc.monto:,.2f}. Cuenta como venta cuando te paguen.", "success")
    return RedirectResponse(f"/cxc/{cxc.id}", status_code=303)


@router.get("/cxc/{cxc_id}")
def cxc_detalle(cxc_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(caja_o_admin)):
    cxc = db.get(CuentaPorCobrar, cxc_id)
    if not cxc:
        flash(request, "Esa cuenta por cobrar no existe.", "error")
        return RedirectResponse("/cxc", status_code=303)
    pagos = [{"p": p, "fecha": a_hora_local(p.fecha), "banco": nombre_banco(db, p.banco_id) if p.forma_pago != "Efectivo" else ""}
             for p in cxc.todos_los_pagos]
    return templates.TemplateResponse("cxc/detalle.html", {
        "request": request, "usuario": usuario, "c": cxc, "pagos": pagos, "hoy": hoy_local(),
        "fecha_local": a_hora_local(cxc.fecha), "formas": C.FORMAS_PAGO_CXC,
        "origen": ("Caja Chica" if cxc.cuenta_salida == "caja_chica" else nombre_banco(db, cxc.banco_id)) if cxc.tipo == CXC_PRESTAMO else "",
    })


@router.post("/cxc/{cxc_id}/pago")
def cxc_pagar(cxc_id: int, request: Request, monto: str = Form(""), forma_pago: str = Form("Efectivo"),
              banco_id: str = Form(""), referencia: str = Form(""),
              mx_efectivo: str = Form(""), mx_tarjeta: str = Form(""), mx_banco_tarjeta: str = Form(""),
              mx_transferencia: str = Form(""), mx_banco_transferencia: str = Form(""), mx_ref_transferencia: str = Form(""),
              db: Session = Depends(get_db), usuario=Depends(caja_o_admin)):
    cxc = db.get(CuentaPorCobrar, cxc_id)
    if not cxc:
        return RedirectResponse("/cxc", status_code=303)
    if forma_pago == FORMA_MIXTO:
        return _pagar_mixto(request, db, usuario, cxc, dict(
            efectivo=mx_efectivo, tarjeta=mx_tarjeta, banco_tarjeta=mx_banco_tarjeta, transferencia=mx_transferencia,
            banco_transferencia=mx_banco_transferencia, ref_transferencia=mx_ref_transferencia))
    if forma_pago == "Efectivo":
        mensaje_caja = verificar_caja(db)
        if mensaje_caja:
            flash(request, f"No se registró el pago en efectivo. {mensaje_caja}", "error")
            return RedirectResponse(f"/cxc/{cxc_id}", status_code=303)
    try:
        pago = C.registrar_pago(db, cxc, monto=monto, forma_pago=forma_pago, banco_id_raw=banco_id,
                                referencia=referencia, usuario_nombre=usuario["nombre_completo"])
    except ValueError as e:
        db.rollback()
        flash(request, str(e), "error")
        return RedirectResponse(f"/cxc/{cxc_id}", status_code=303)
    db.commit()
    destino = "la caja" if forma_pago == "Efectivo" else nombre_banco(db, pago.banco_id)
    extra = " La cuenta quedó pagada." if cxc.estado == CXC_PAGADA else f" Falta L {cxc.saldo:,.2f}."
    flash(request, f"Pago de L {pago.monto:,.2f} en {forma_pago} registrado (entra a {destino}).{extra}", "success")
    return RedirectResponse(f"/cxc/{cxc_id}", status_code=303)


def _pagar_mixto(request, db, usuario, cxc, campos):
    """Un pago en varias formas = un pago de CxC por cada forma (cada uno a su
    lugar: efectivo a la caja, tarjeta/transferencia al banco elegido)."""
    try:
        partes = leer_partes(**campos)
        if total_partes(partes) > C.q(cxc.saldo):
            raise ValueError(f"El pago (L {total_partes(partes):,.2f}) es mayor que lo que falta por cobrar (L {C.q(cxc.saldo):,.2f}).")
    except ValueError as e:
        flash(request, str(e), "error")
        return RedirectResponse(f"/cxc/{cxc.id}", status_code=303)
    if any(p["forma"] == "Efectivo" for p in partes):
        mensaje_caja = verificar_caja(db)
        if mensaje_caja:
            flash(request, f"No se registró el pago: lleva efectivo. {mensaje_caja}", "error")
            return RedirectResponse(f"/cxc/{cxc.id}", status_code=303)
    try:
        for p in partes:
            C.registrar_pago(db, cxc, monto=p["monto"], forma_pago=p["forma"], banco_id_raw=p["banco_raw"],
                             referencia=p["referencia"], usuario_nombre=usuario["nombre_completo"])
    except ValueError as e:
        db.rollback()
        flash(request, str(e), "error")
        return RedirectResponse(f"/cxc/{cxc.id}", status_code=303)
    db.commit()
    extra = " La cuenta quedó pagada." if cxc.estado == CXC_PAGADA else f" Falta L {cxc.saldo:,.2f}."
    ef = next((p["monto"] for p in partes if p["forma"] == "Efectivo"), C.CERO)
    flash(request, f"Pago mixto de L {total_partes(partes):,.2f} registrado ({texto_partes(partes)}). "
                   f"A la caja entran L {ef:,.2f} en efectivo; lo demás, al banco.{extra}", "success")
    return RedirectResponse(f"/cxc/{cxc.id}", status_code=303)


@router.post("/cxc/{cxc_id}/pagos/{pago_id}/anular")
def cxc_anular_pago(cxc_id: int, pago_id: int, request: Request, motivo: str = Form(""),
                    db: Session = Depends(get_db), usuario=Depends(caja_o_admin)):
    pago = db.get(CxCPago, pago_id)
    if not pago or pago.cxc_id != cxc_id:
        return RedirectResponse(f"/cxc/{cxc_id}", status_code=303)
    try:
        C.anular_pago(db, pago, motivo, usuario["nombre_completo"])
    except ValueError as e:
        db.rollback()
        flash(request, str(e), "error")
        return RedirectResponse(f"/cxc/{cxc_id}", status_code=303)
    db.commit()
    flash(request, f"Pago de L {pago.monto:,.2f} anulado: ya no cuenta en caja, banco ni reportes.", "success")
    return RedirectResponse(f"/cxc/{cxc_id}", status_code=303)


@router.post("/cxc/{cxc_id}/anular")
def cxc_anular(cxc_id: int, request: Request, motivo: str = Form(""), db: Session = Depends(get_db), usuario=Depends(caja_o_admin)):
    cxc = db.get(CuentaPorCobrar, cxc_id)
    if not cxc:
        return RedirectResponse("/cxc", status_code=303)
    try:
        C.anular_cuenta(db, cxc, motivo, usuario["nombre_completo"])
    except ValueError as e:
        db.rollback()
        flash(request, str(e), "error")
        return RedirectResponse(f"/cxc/{cxc_id}", status_code=303)
    db.commit()
    flash(request, f"{cxc.numero} anulada." + (" El dinero del préstamo volvió a contar en su cuenta." if cxc.tipo == CXC_PRESTAMO else ""), "success")
    return RedirectResponse(f"/cxc/{cxc_id}", status_code=303)
