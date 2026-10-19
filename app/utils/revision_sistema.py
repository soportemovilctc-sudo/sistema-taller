"""Revisión del sistema: busca datos que no cuadran en Cajas, Dinero,
Inventario, Órdenes y Facturas, y explica cada uno en palabras simples.

Solo LEE: no cambia nada. Las correcciones las hace el administrador con
los botones de la pantalla (ver app/routers/revision.py), cada una sobre
un caso concreto y después de confirmar.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models import (
    TurnoCaja, MovimientoFinanciero, Factura, OrdenServicio, Producto,
    TURNO_ABIERTO, CATEGORIA_DEPOSITO_BANCO, CATEGORIA_VENTA_FACTURADA,
)
from app.utils.calculations import to_decimal, calcular_recargo, calcular_total, calcular_saldo
from app.utils.caja_calculos import calcular_liquidez, obtener_saldo_inicial, mes_actual
from app.utils.turnos_caja import (
    calcular_resumen_turno, a_hora_local, es_turno_de_dia_anterior, fecha_local,
)

CERO = Decimal("0.00")
REFERENCIAS_FUERA_DE_CAJA = ("Manual", "")  # Reportes > Egresos/Ingresos y Contabilidad


def _l(v) -> str:
    return f"L {to_decimal(v or 0):,.2f}"


def _problema(nivel, titulo, detalle="", items=None, acciones=None, enlace=None, ancla=""):
    return {"nivel": nivel, "titulo": titulo, "detalle": detalle, "items": items or [],
            "acciones": acciones or [], "enlace": enlace, "ancla": ancla}


def _accion(texto, url, confirmar, campos=None, pide_motivo=False, estilo="btn-outline"):
    return {"texto": texto, "url": url, "confirmar": confirmar, "campos": campos or {},
            "pide_motivo": pide_motivo, "estilo": estilo}


def _origen(m: MovimientoFinanciero) -> str:
    if m.referencia == "Manual":
        return "Reportes (a mano)"
    if not m.referencia:
        return "Contabilidad (a mano)"
    if m.referencia == "Caja":
        return "Caja"
    return m.referencia


# ---------------------------------------------------------------------------
# Cajas (aperturas y cierres)
# ---------------------------------------------------------------------------
def _revisar_cajas(db: Session) -> list[dict]:
    problemas = []
    turnos = db.query(TurnoCaja).order_by(TurnoCaja.fecha_apertura.desc()).limit(200).all()
    for t in turnos:
        r = calcular_resumen_turno(db, t)
        dia = a_hora_local(t.fecha_apertura).strftime("%d/%m/%Y")
        nombre = f"Caja #{t.id} del {dia}"
        cerrada = t.estado != TURNO_ABIERTO
        enlace = ("Ver la caja", f"/caja/turnos/{t.id}")
        ancla = f"caja-{t.id}"

        if r["efectivo_esperado"] < 0:
            entradas = r["total_pagos_efectivo"] + r["total_ingresos_efectivo"]
            detalle = (f"Efectivo inicial {_l(r['monto_inicial'])} + entradas {_l(entradas)} − salidas "
                       f"{_l(r['total_salidas_efectivo'])} = {_l(r['efectivo_esperado'])}. Es imposible tener efectivo negativo: "
                       "o el efectivo inicial quedó más bajo de lo que había, o alguna salida no salió de esta caja.")
            acciones = []
            if cerrada and t.efectivo_contado is not None:
                sugerido = (to_decimal(t.efectivo_contado) - (r["efectivo_esperado"] - r["monto_inicial"])).quantize(Decimal("0.01"))
                if sugerido > 0:
                    detalle += (f" Para que cuadre con lo contado ({_l(t.efectivo_contado)}), el efectivo inicial "
                                f"tendría que haber sido {_l(sugerido)}.")
                    acciones.append(_accion(
                        f"Poner {_l(sugerido)} como efectivo inicial", f"/revision/caja/{t.id}/efectivo-inicial",
                        f"¿Cambiar el efectivo inicial de la caja #{t.id} de {_l(r['monto_inicial'])} a {_l(sugerido)}? Queda en la bitácora.",
                        campos={"valor": str(sugerido)}, pide_motivo=True, estilo="btn-primary"))
            items = [
                {"texto": f"{a_hora_local(m.fecha).strftime('%d/%m %I:%M %p')} · {m.categoria} · {m.descripcion or ''} · "
                          f"{_l(m.monto)} · registrado por {m.usuario_nombre or '-'} desde {_origen(m)}",
                 "accion": _accion("Quitar de esta caja", f"/revision/caja/{t.id}/quitar/mov/{m.id}",
                                   "¿Quitar esta salida del cierre de esta caja? No se borra: sigue en la contabilidad.",
                                   pide_motivo=True)}
                for m in sorted(r["salidas_efectivo"], key=lambda x: -to_decimal(x.monto))[:15]
            ]
            problemas.append(_problema("error", f"{nombre}: el efectivo esperado sale negativo ({_l(r['efectivo_esperado'])})",
                                       detalle, items, acciones, enlace, ancla))

        if cerrada and t.efectivo_esperado is not None and to_decimal(t.efectivo_esperado) != r["efectivo_esperado"]:
            problemas.append(_problema(
                "aviso", f"{nombre}: el cierre guardado ya no coincide con sus registros",
                f"Al cerrarla se guardó un esperado de {_l(t.efectivo_esperado)}; con lo que tiene registrado hoy da "
                f"{_l(r['efectivo_esperado'])} (algún registro cambió después del cierre).",
                acciones=[_accion("Recalcular el cierre", f"/revision/caja/{t.id}/recalcular",
                                  f"¿Recalcular el esperado y la diferencia de la caja #{t.id}?")],
                enlace=enlace, ancla=ancla))

        fuera = [m for m in r["movimientos"] if not m.excluir_de_contabilidad and m.referencia in REFERENCIAS_FUERA_DE_CAJA]
        if fuera:
            items = [
                {"texto": f"{a_hora_local(m.fecha).strftime('%d/%m %I:%M %p')} · {'Ingreso' if m.tipo == 'ingreso' else 'Egreso'} · "
                          f"{m.categoria} · {m.descripcion or ''} · {_l(m.monto)} · {'Caja Chica' if m.cuenta == 'caja_chica' else 'Banco'} · "
                          f"por {m.usuario_nombre or '-'} desde {_origen(m)}",
                 "accion": _accion("Quitar de esta caja", f"/revision/caja/{t.id}/quitar/mov/{m.id}",
                                   "¿Quitar este registro del cierre de esta caja? No se borra: sigue en la contabilidad.",
                                   pide_motivo=True)}
                for m in fuera
            ]
            problemas.append(_problema(
                "aviso", f"{nombre}: tiene {len(fuera)} registro(s) hechos fuera de Caja",
                "Se registraron desde Reportes o Contabilidad mientras la caja estaba abierta, así que cuentan en su cierre. "
                "Si ese dinero no entró ni salió de la gaveta de la cajera, quítalos de esta caja.",
                items, enlace=enlace, ancla=ancla))

        if not cerrada and es_turno_de_dia_anterior(t):
            problemas.append(_problema("aviso", f"{nombre} sigue abierta",
                                       "Hay que cerrarla con el conteo del efectivo para poder abrir la de hoy.",
                                       enlace=("Ir a Apertura y cierre", "/caja/turnos"), ancla=ancla))
    return problemas


# ---------------------------------------------------------------------------
# Dinero (Caja Chica, Banco, facturas, depósitos)
# ---------------------------------------------------------------------------
def _revisar_dinero(db: Session) -> list[dict]:
    problemas = []
    anio, mes = mes_actual()
    liq = calcular_liquidez(db, anio, mes)
    if not obtener_saldo_inicial(db, anio, mes):
        problemas.append(_problema("aviso", "Este mes no tiene saldo inicial configurado",
                                   "Caja Chica y Banco se están calculando desde 0 este mes.",
                                   enlace=("Configurar en el Panel gerencial", "/caja/panel")))
    if liq["caja_chica_actual"] < 0:
        problemas.append(_problema("error", f"Caja Chica está en negativo ({_l(liq['caja_chica_actual'])})",
                                   "No puede haber menos de cero efectivo. Revisa el saldo inicial del mes y las salidas grandes.",
                                   enlace=("Ver Panel gerencial", "/caja/panel")))
    if liq["banco_actual"] < 0:
        problemas.append(_problema("aviso", f"Banco está en negativo ({_l(liq['banco_actual'])})",
                                   "Revisa el saldo inicial de Banco del mes.", enlace=("Ver Panel gerencial", "/caja/panel")))

    anuladas = (
        db.query(Factura).filter(Factura.anulada == True)  # noqa: E712
        .all()
    )
    for f in anuladas:
        vivos = db.query(MovimientoFinanciero).filter(
            MovimientoFinanciero.factura_id == f.id, MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
        ).all()
        if vivos:
            problemas.append(_problema(
                "error", f"La factura anulada {f.numero_documento} todavía cuenta como ingreso ({_l(sum(to_decimal(m.monto) for m in vivos))})",
                "Una factura anulada no debe sumar en ingresos ni en Caja.",
                acciones=[_accion("Dejar de contarla", f"/revision/factura/{f.id}/excluir-ingresos",
                                  f"¿Excluir los ingresos de la factura anulada {f.numero_documento}? No se borran.")],
                enlace=("Ver factura", f"/facturas/{f.id}")))

    # Solo desde que las Facturas generan el ingreso de las órdenes (el primer
    # "Venta facturada (orden)"): las facturas de antes cobraban su ingreso con
    # las categorías viejas, y ese registro contable no se toca.
    desde_facturado = db.query(func.min(MovimientoFinanciero.fecha)).filter(
        MovimientoFinanciero.categoria == CATEGORIA_VENTA_FACTURADA).scalar()
    activas_orden = [] if desde_facturado is None else db.query(Factura).filter(
        Factura.anulada == False, Factura.orden_id.isnot(None), Factura.fecha_emision >= desde_facturado,  # noqa: E712
    ).all()
    ids_con_ingreso = {
        fid for (fid,) in db.query(MovimientoFinanciero.factura_id).filter(
            MovimientoFinanciero.factura_id.isnot(None), MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
        ).distinct().all()
    }
    for f in activas_orden:
        if f.id not in ids_con_ingreso and to_decimal(f.total) > 0:
            problemas.append(_problema(
                "error", f"La factura {f.numero_documento} ({_l(f.total)}) no tiene su ingreso registrado",
                "La venta no está sumando en Ingresos, Caja/Banco ni en los Estados Financieros.",
                acciones=[_accion("Registrar el ingreso que falta", f"/revision/factura/{f.id}/crear-ingreso",
                                  f"¿Registrar el ingreso de la factura {f.numero_documento} con su fecha original, repartido según cómo se cobró la orden?",
                                  estilo="btn-primary")],
                enlace=("Ver factura", f"/facturas/{f.id}")))

    depositos = db.query(MovimientoFinanciero).filter(MovimientoFinanciero.categoria == CATEGORIA_DEPOSITO_BANCO).all()
    por_id = {m.id: m for m in depositos}
    malos = 0
    for m in depositos:
        par = por_id.get(m.movimiento_vinculado_id) if m.movimiento_vinculado_id else None
        if par is None or {m.cuenta, par.cuenta} != {"caja_chica", "banco"} or to_decimal(m.monto) != to_decimal(par.monto):
            malos += 1
    if malos:
        problemas.append(_problema("error", f"Hay {malos} fila(s) de Depósito bancario mal formadas",
                                   "Un depósito debe ser una salida de Caja Chica y una entrada a Banco por el mismo monto.",
                                   enlace=("Abrir la auditoría de depósitos", "/caja/conciliacion/depositos/auditoria")))

    from app.utils.depositos import sospechosos
    sosp = sospechosos(db)
    if sosp:
        total_s = sum((to_decimal(m.monto) for m in sosp), CERO)
        problemas.append(_problema(
            "error", f"{len(sosp)} depósito(s) al banco que no salieron de Caja Chica ({_l(total_s)})",
            "Se registraron como una entrada al banco (cobro o ingreso), no como Depósito bancario: el dinero sigue sumando en la caja "
            "y además cuenta como venta. Al convertirlos, se restan de Caja Chica (y del cierre de esa caja) y dejan de contar como ingreso. "
            "Si alguno era un cliente que pagó depositando en el banco, NO lo conviertas. También puedes convertir cualquier otra entrada "
            "desde el Estado de cuenta bancario.",
            items=[{"texto": f"#{m.id} · {a_hora_local(m.fecha).strftime('%d/%m/%Y %I:%M %p')} · {_l(m.monto)} · {m.categoria}"
                             + (f" · {m.metodo_pago}" if m.metodo_pago else "") + f" · {(m.cliente_nombre or m.descripcion or '').strip()[:80]}"
                             + (f" · por {m.usuario_nombre}" if m.usuario_nombre else ""),
                    "enlace": None} for m in sosp[:60]],
            acciones=[_accion(f"Convertir #{m.id} ({_l(m.monto)})", f"/revision/deposito/{m.id}/convertir",
                              f"¿Convertir la entrada #{m.id} de {_l(m.monto)} en Depósito bancario? Se resta de Caja Chica y deja de contar como venta.",
                              estilo="btn-primary") for m in sosp[:60]]
                     + ([_accion("Convertir todos", "/revision/depositos/convertir-todos",
                                 f"¿Convertir los {len(sosp)} en Depósito bancario? Se restan {_l(total_s)} de Caja Chica.",
                                 estilo="btn-primary")] if len(sosp) > 1 else []),
            enlace=("Ver Estado de cuenta bancario", "/banco/estado-cuenta?tipo=entradas"), ancla="depositos-sin-caja"))

    sin_forma = db.query(MovimientoFinanciero).filter(
        MovimientoFinanciero.tipo == "gasto", MovimientoFinanciero.referencia == "Manual",
        MovimientoFinanciero.metodo_pago.is_(None), MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    ).count()
    if sin_forma:
        problemas.append(_problema("aviso", f"{sin_forma} egreso(s) registrados a mano sin forma de pago",
                                   "Sin forma de pago se cuentan como efectivo de Caja Chica. Elige si fue efectivo o transferencia.",
                                   enlace=("Completarlos en Reportes > Egresos", "/reportes?tipo=gastos")))
    return problemas


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------
def _revisar_inventario(db: Session) -> list[dict]:
    problemas = []
    negativos = db.query(Producto).filter(Producto.existencia < 0).order_by(Producto.nombre).all()
    if negativos:
        problemas.append(_problema(
            "error", f"{len(negativos)} producto(s) con existencia negativa",
            "No se puede tener menos de cero unidades. Haz un conteo y ajústalos.",
            items=[{"texto": f"{p.codigo} · {p.nombre} · existencia {p.existencia}"} for p in negativos[:30]],
            enlace=("Hacer un ajuste de inventario", "/ajustes-inventario/nuevo")))
    sin_costo = db.query(Producto).filter(Producto.existencia > 0, (Producto.costo == None) | (Producto.costo <= 0)).order_by(Producto.nombre).all()  # noqa: E711
    if sin_costo:
        problemas.append(_problema(
            "aviso", f"{len(sin_costo)} producto(s) con existencia pero sin costo",
            "Sin costo, el inventario y el costo de ventas de los Estados Financieros salen en 0 para esos productos.",
            items=[{"texto": f"{p.codigo} · {p.nombre} · {p.existencia} unidades", "enlace": f"/inventario/{p.id}/editar"} for p in sin_costo[:30]],
            enlace=("Ver inventario", "/inventario")))
    return problemas


# ---------------------------------------------------------------------------
# Órdenes
# ---------------------------------------------------------------------------
def _revisar_ordenes(db: Session) -> list[dict]:
    problemas = []
    ordenes = (
        db.query(OrdenServicio)
        .options(selectinload(OrdenServicio.pagos), selectinload(OrdenServicio.repuestos), selectinload(OrdenServicio.servicios_extra))
        .all()
    )
    descuadradas, entregadas_con_saldo, sobrepagadas = [], [], []
    for o in ordenes:
        recargo = calcular_recargo(o.cotizacion, o.recargo_pct)
        repuestos = sum((to_decimal(r.subtotal) for r in o.repuestos), CERO)
        servicios = sum((to_decimal(s.subtotal) for s in o.servicios_extra), CERO)
        total = calcular_total(o.cotizacion, recargo, repuestos, servicios)
        abonado = sum((to_decimal(p.monto) for p in o.pagos), CERO)
        saldo = calcular_saldo(total, abonado)
        if (to_decimal(o.total or 0) != to_decimal(total) or to_decimal(o.abonado or 0) != to_decimal(abonado)
                or to_decimal(o.saldo or 0) != to_decimal(saldo)):
            descuadradas.append((o, total, abonado, saldo))
        if abonado > total:
            sobrepagadas.append((o, total, abonado))
        if o.estado == "ENTREGADO" and saldo > 0:
            entregadas_con_saldo.append((o, saldo))
    if descuadradas:
        problemas.append(_problema(
            "error", f"{len(descuadradas)} orden(es) con total, abonado o saldo mal calculado",
            "Lo guardado en la orden no coincide con la suma de sus repuestos, servicios y abonos.",
            items=[{"texto": f"{o.numero_orden}: guardado total {_l(o.total)} / abonado {_l(o.abonado)} / saldo {_l(o.saldo)} → "
                             f"correcto {_l(t)} / {_l(a)} / {_l(s)}",
                    "enlace": f"/ordenes/{o.id}",
                    "accion": _accion("Recalcular", f"/revision/orden/{o.id}/recalcular", f"¿Recalcular la orden {o.numero_orden}?")}
                   for o, t, a, s in descuadradas[:40]]))
    if sobrepagadas:
        problemas.append(_problema(
            "error", f"{len(sobrepagadas)} orden(es) con más abonos que su total",
            "Se cobró más de lo que cuesta la orden. Revisa si un abono está repetido o si falta agregar algo a la orden.",
            items=[{"texto": f"{o.numero_orden}: total {_l(t)}, abonado {_l(a)}", "enlace": f"/ordenes/{o.id}"} for o, t, a in sobrepagadas[:40]]))
    if entregadas_con_saldo:
        problemas.append(_problema(
            "aviso", f"{len(entregadas_con_saldo)} orden(es) entregadas con saldo pendiente",
            "Se entregó el equipo pero falta cobrar.",
            items=[{"texto": f"{o.numero_orden}: saldo {_l(s)}", "enlace": f"/ordenes/{o.id}"} for o, s in entregadas_con_saldo[:40]]))
    return problemas


def revisar_sistema(db: Session) -> dict:
    secciones = [
        {"clave": "cajas", "titulo": "Cajas (aperturas y cierres)", "problemas": _revisar_cajas(db)},
        {"clave": "dinero", "titulo": "Dinero (Caja Chica, Banco, facturas y depósitos)", "problemas": _revisar_dinero(db)},
        {"clave": "inventario", "titulo": "Inventario", "problemas": _revisar_inventario(db)},
        {"clave": "ordenes", "titulo": "Órdenes", "problemas": _revisar_ordenes(db)},
    ]
    errores = sum(1 for s in secciones for p in s["problemas"] if p["nivel"] == "error")
    avisos = sum(1 for s in secciones for p in s["problemas"] if p["nivel"] == "aviso")
    return {"secciones": secciones, "errores": errores, "avisos": avisos,
            "revisado_en": a_hora_local(datetime.utcnow())}
