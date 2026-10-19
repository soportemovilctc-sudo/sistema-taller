"""Cálculos de las mejoras tomadas de Zafra: cuentas por cobrar con
antigüedad, declaración de ISV, reorden de inventario, margen del
inventario y cotizaciones."""
import urllib.parse
from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session, selectinload

from app.models import (
    OrdenServicio, Factura, RecepcionCompra, Producto, SolicitudCompra, SolicitudCompraDetalle,
    Cotizacion, CotizacionDetalle, Proveedor, COMPRA_PENDIENTE, COMPRA_PARCIAL,
)
from app.utils.calculations import to_decimal
from app.utils.turnos_caja import a_hora_local, hoy_local, inicio_dia_local_en_utc

CERO = Decimal("0.00")
CENT = Decimal("0.01")


def q(v) -> Decimal:
    return to_decimal(v or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def link_whatsapp(telefono: str, mensaje: str) -> str:
    numero = "".join(ch for ch in (telefono or "") if ch.isdigit())
    if len(numero) == 8:  # Honduras
        numero = "504" + numero
    return f"https://wa.me/{numero}?text={urllib.parse.quote(mensaje)}" if numero else ""


# ---------------------------------------------------------------------------
# Cuentas por cobrar con antigüedad
# ---------------------------------------------------------------------------
TRAMOS = (("0-30", "0 a 30 días", 0, 30), ("31-60", "31 a 60 días", 31, 60), ("61-90", "61 a 90 días", 61, 90), ("90+", "Más de 90 días", 91, 10 ** 6))


def tramo_de(dias: int) -> str:
    for clave, _, a, b in TRAMOS:
        if a <= dias <= b:
            return clave
    return "90+"


def cuentas_por_cobrar(db: Session, tramo: str = "", busqueda: str = "") -> dict:
    hoy = hoy_local()
    ordenes = (db.query(OrdenServicio).options(selectinload(OrdenServicio.cliente))
               .filter(OrdenServicio.saldo > 0, OrdenServicio.estado != "CANCELADO")
               .order_by(OrdenServicio.fecha.asc()).all())
    filas, totales = [], OrderedDict((t[0], {"nombre": t[1], "n": 0, "saldo": CERO}) for t in TRAMOS)
    for o in ordenes:
        dias = (hoy - a_hora_local(o.fecha).date()).days
        t = tramo_de(dias)
        cli = o.cliente
        nombre = cli.nombre if cli else "—"
        if busqueda and busqueda.lower() not in f"{nombre} {o.numero_orden} {(cli.telefono if cli else '')}".lower():
            continue
        totales[t]["n"] += 1
        totales[t]["saldo"] += q(o.saldo)
        if tramo and t != tramo:
            continue
        tel = (cli.whatsapp or cli.telefono or "") if cli else ""
        msj = (f"Hola {nombre}, le saludamos de parte del taller. Le recordamos que su orden {o.numero_orden} "
               f"({o.marca or ''} {o.modelo or ''}) tiene un saldo pendiente de L {q(o.saldo):,.2f}. ¡Gracias!")
        filas.append({"orden": o, "cliente": nombre, "cliente_id": o.cliente_id, "telefono": tel, "dias": dias, "tramo": t,
                      "total": q(o.total), "abonado": q(o.abonado), "saldo": q(o.saldo), "whatsapp": link_whatsapp(tel, msj)})
    por_cliente = OrderedDict()
    for f in filas:
        c = por_cliente.setdefault(f["cliente_id"], {"cliente": f["cliente"], "telefono": f["telefono"], "n": 0, "saldo": CERO, "dias_max": 0})
        c["n"] += 1
        c["saldo"] += f["saldo"]
        c["dias_max"] = max(c["dias_max"], f["dias"])
    total = sum((v["saldo"] for v in totales.values()), CERO)
    return {"filas": filas, "tramos": totales, "total": total, "n": sum(v["n"] for v in totales.values()),
            "por_cliente": sorted(por_cliente.values(), key=lambda c: -c["saldo"])}


# ---------------------------------------------------------------------------
# Declaración de ISV del mes
# ---------------------------------------------------------------------------
def rango_mes(anio: int, mes: int):
    inicio = date(anio, mes, 1)
    fin = date(anio + (mes == 12), (mes % 12) + 1, 1)
    return inicio, fin, inicio_dia_local_en_utc(inicio), inicio_dia_local_en_utc(fin)


def declaracion_isv(db: Session, anio: int, mes: int) -> dict:
    d_ini, d_fin, inicio, fin = rango_mes(anio, mes)
    facturas = (db.query(Factura).filter(Factura.fecha_emision >= inicio, Factura.fecha_emision < fin, Factura.anulada == False)  # noqa: E712
                .order_by(Factura.fecha_emision).all())
    anuladas = db.query(Factura).filter(Factura.fecha_emision >= inicio, Factura.fecha_emision < fin, Factura.anulada == True).count()  # noqa: E712

    def resumen(lista):
        return {"n": len(lista), "exento": q(sum((to_decimal(f.importe_exento or 0) for f in lista), CERO)),
                "gravado": q(sum((to_decimal(f.importe_gravado or 0) for f in lista), CERO)),
                "isv": q(sum((to_decimal(f.isv_monto or 0) for f in lista), CERO)),
                "total": q(sum((to_decimal(f.total or 0) for f in lista), CERO))}

    fiscales = [f for f in facturas if f.tipo == "fiscal"]
    internas = [f for f in facturas if f.tipo != "fiscal"]
    recepciones = (db.query(RecepcionCompra).filter(RecepcionCompra.fecha >= inicio, RecepcionCompra.fecha < fin,
                                                    RecepcionCompra.anulada == False)  # noqa: E712
                   .order_by(RecepcionCompra.fecha).all())
    con_isv = [r for r in recepciones if to_decimal(r.isv or 0) > 0]
    compras = {"n": len(con_isv), "base": q(sum((to_decimal(r.subtotal or 0) for r in con_isv), CERO)),
               "isv": q(sum((to_decimal(r.isv or 0) for r in con_isv), CERO)),
               "total": q(sum((to_decimal(r.total or 0) for r in con_isv), CERO)),
               "sin_isv": q(sum((to_decimal(r.subtotal or 0) for r in recepciones if to_decimal(r.isv or 0) <= 0), CERO))}
    rf, ri = resumen(fiscales), resumen(internas)
    a_pagar = q(rf["isv"] - compras["isv"])
    a_pagar_todas = q(rf["isv"] + ri["isv"] - compras["isv"])
    return {"anio": anio, "mes": mes, "desde": d_ini, "hasta": d_fin - timedelta(days=1),
            "fiscales": rf, "internas": ri, "compras": compras, "anuladas": anuladas,
            "a_pagar": a_pagar, "a_pagar_todas": a_pagar_todas,
            "lista_fiscales": fiscales, "lista_internas": internas, "lista_compras": con_isv}


# ---------------------------------------------------------------------------
# Reorden de inventario
# ---------------------------------------------------------------------------
def pendiente_por_producto(db: Session) -> dict:
    pend = {}
    for d in (db.query(SolicitudCompraDetalle).join(SolicitudCompra, SolicitudCompraDetalle.solicitud_id == SolicitudCompra.id)
              .filter(SolicitudCompra.estado.in_([COMPRA_PENDIENTE, COMPRA_PARCIAL])).all()):
        pend[d.producto_id] = pend.get(d.producto_id, 0) + max(0, d.pendiente)
    return pend


def reorden(db: Session, categoria: str = "") -> list:
    pend = pendiente_por_producto(db)
    consulta = db.query(Producto).filter(Producto.estado == "activo", Producto.stock_minimo > 0)
    if categoria:
        consulta = consulta.filter(Producto.categoria == categoria)
    filas = []
    for p in consulta.order_by(Producto.categoria, Producto.nombre).all():
        if (p.existencia or 0) > (p.stock_minimo or 0):
            continue
        objetivo = p.stock_maximo if (p.stock_maximo or 0) > (p.stock_minimo or 0) else (p.stock_minimo or 0) * 2
        ya = pend.get(p.id, 0)
        sugerido = max(0, objetivo - (p.existencia or 0) - ya)
        filas.append({"producto": p, "objetivo": objetivo, "pendiente": ya, "sugerido": sugerido,
                      "costo": q(p.costo), "valor": q(to_decimal(p.costo or 0) * sugerido), "agotado": (p.existencia or 0) <= 0})
    filas.sort(key=lambda f: (not f["agotado"], f["producto"].categoria or "", f["producto"].nombre))
    return filas


# ---------------------------------------------------------------------------
# Margen y costo del inventario
# ---------------------------------------------------------------------------
def margen(p) -> Decimal | None:
    precio, costo = to_decimal(p.precio_venta or 0), to_decimal(p.costo or 0)
    if precio <= 0:
        return None
    return ((precio - costo) / precio * 100).quantize(Decimal("0.1"))


def resumen_inventario(productos) -> dict:
    por_cat = OrderedDict()
    for p in productos:
        c = por_cat.setdefault(p.categoria or "Sin categoría", {"productos": 0, "unidades": 0, "costo": CERO, "venta": CERO})
        c["productos"] += 1
        c["unidades"] += p.existencia or 0
        c["costo"] += q(to_decimal(p.costo or 0) * (p.existencia or 0))
        c["venta"] += q(to_decimal(p.precio_venta or 0) * (p.existencia or 0))
    for c in por_cat.values():
        c["margen"] = ((c["venta"] - c["costo"]) / c["venta"] * 100).quantize(Decimal("0.1")) if c["venta"] > 0 else None
    tot_costo = sum((c["costo"] for c in por_cat.values()), CERO)
    tot_venta = sum((c["venta"] for c in por_cat.values()), CERO)
    return {"por_categoria": sorted(por_cat.items(), key=lambda kv: -kv[1]["costo"]), "costo": tot_costo, "venta": tot_venta,
            "ganancia": tot_venta - tot_costo,
            "margen": ((tot_venta - tot_costo) / tot_venta * 100).quantize(Decimal("0.1")) if tot_venta > 0 else None}


# ---------------------------------------------------------------------------
# Cotizaciones
# ---------------------------------------------------------------------------
def siguiente_numero_cotizacion(db: Session) -> str:
    from app.utils.numbering import siguiente_numero
    ultimo = db.query(Cotizacion).order_by(Cotizacion.id.desc()).first()
    return siguiente_numero(ultimo.numero if ultimo else None, "COT")


def crear_cotizacion(db: Session, datos: dict, lineas: list, usuario_nombre: str, tasa) -> tuple:
    """lineas: [{producto_id, descripcion, cantidad, precio}] con el precio como lo escribió el usuario
    (con ISV si datos['precios_con_isv'])."""
    errores, detalles = [], []
    tasa = to_decimal(tasa or 0)
    con_isv = bool(datos.get("precios_con_isv"))
    for i, l in enumerate(lineas, start=1):
        desc = (l.get("descripcion") or "").strip()
        pid = None
        if (l.get("producto_id") or "").strip():
            try:
                prod = db.get(Producto, int(l["producto_id"]))
            except ValueError:
                prod = None
            if prod:
                pid = prod.id
                desc = desc or prod.nombre
        if not desc:
            continue
        try:
            cant = int((l.get("cantidad") or "1").strip() or 1)
            precio = to_decimal((l.get("precio") or "0").replace(",", "").strip() or 0)
        except Exception:  # noqa: BLE001
            errores.append(f"Línea {i}: cantidad o precio inválido.")
            continue
        if cant <= 0 or precio < 0:
            errores.append(f"Línea {i}: la cantidad debe ser mayor a 0 y el precio no puede ser negativo.")
            continue
        sin_isv = (precio / (1 + tasa / 100)).quantize(CENT) if con_isv else precio.quantize(CENT)
        detalles.append(CotizacionDetalle(producto_id=pid, descripcion=desc[:200], cantidad=cant, precio_unitario=sin_isv,
                                          subtotal=q(sin_isv * cant)))
    if not detalles and not errores:
        errores.append("Agrega al menos un producto o servicio.")
    nombre = (datos.get("cliente_nombre") or "").strip()
    cliente_id = None
    if (datos.get("cliente_id") or "").strip():
        from app.models import Cliente
        try:
            cli = db.get(Cliente, int(datos["cliente_id"]))
        except ValueError:
            cli = None
        if cli:
            cliente_id = cli.id
            nombre = nombre or cli.nombre
    if not nombre:
        nombre = "Consumidor final"
    if errores:
        return None, errores
    subtotal = q(sum((d.subtotal for d in detalles), CERO))
    isv = q(subtotal * tasa / 100)
    total = q(subtotal + isv)
    if con_isv:  # que el total sea exactamente lo que se escribió (sin centavos de diferencia por redondeo)
        escrito = q(sum((to_decimal((l.get("precio") or "0").replace(",", "") or 0) * int((l.get("cantidad") or "1") or 1)
                         for l in lineas if (l.get("descripcion") or "").strip() or (l.get("producto_id") or "").strip()), CERO))
        if abs(escrito - total) <= Decimal("0.05"):
            total = escrito
            isv = q(total - subtotal)
    try:
        validez = max(1, int(datos.get("validez_dias") or 15))
    except ValueError:
        validez = 15
    cot = Cotizacion(numero=siguiente_numero_cotizacion(db), fecha=datetime.utcnow(), cliente_id=cliente_id, cliente_nombre=nombre[:150],
                     cliente_telefono=(datos.get("cliente_telefono") or "").strip()[:30], validez_dias=validez,
                     notas=(datos.get("notas") or "").strip(), precios_con_isv=con_isv, subtotal=subtotal, isv=isv, total=total,
                     usuario_nombre=usuario_nombre)
    cot.detalles = detalles
    db.add(cot)
    db.flush()
    return cot, []


def mensaje_whatsapp_cotizacion(cot, nombre_taller: str, moneda: str = "L") -> str:
    lineas = [f"*{nombre_taller}* — Cotización {cot.numero}", f"Cliente: {cot.cliente_nombre}", ""]
    tasa = (to_decimal(cot.isv) / to_decimal(cot.subtotal) * 100) if to_decimal(cot.subtotal or 0) > 0 else Decimal("0")
    for d in cot.detalles:
        con = q(to_decimal(d.precio_unitario) * (1 + tasa / 100)) * d.cantidad
        lineas.append(f"• {d.cantidad} x {d.descripcion}: {moneda} {q(con):,.2f}")
    lineas += ["", f"*Total: {moneda} {q(cot.total):,.2f}* (ISV incluido)", f"Válida hasta el {a_hora_local(cot.vence).strftime('%d/%m/%Y')}."]
    if cot.notas:
        lineas.append(cot.notas)
    return "\n".join(lineas)


def proveedores_activos(db: Session):
    return db.query(Proveedor).filter(Proveedor.activo == True).order_by(Proveedor.nombre).all()  # noqa: E712
