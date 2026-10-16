"""Ajustes de inventario y costo de cada movimiento.

  * _completar_costos (listener): a todo MovimientoInventario, DetalleVenta y
    OrdenRepuesto NUEVO le guarda el costo del producto en ese momento (y,
    a los movimientos de entrada/salida, la existencia que había antes).
    Así los reportes en lempiras y el costo de ventas no dependen del costo
    que tenga el producto después. Lo anterior a este módulo queda igual.
  * aplicar_ajuste: crea un ajuste (AJ-000001) de uno o varios productos.
  * revertir_ajuste: deshace un ajuste con otro ajuste inverso.
  * reporte_ajustes: historial/reportes de ajustes en unidades y lempiras,
    incluidos los ajustes rápidos de un solo producto hechos antes.

Un ajuste NO es dinero: no crea MovimientoFinanciero ni toca Caja/Banco.
"""
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import (
    Producto, MovimientoInventario, DetalleVenta, OrdenRepuesto,
    AjusteInventario, AjusteInventarioDetalle, MOTIVO_REVERSION_AJUSTE,
)
from app.utils.calculations import to_decimal
from app.utils.numbering import siguiente_numero
from app.utils.turnos_caja import a_hora_local

CERO = Decimal("0.00")
MODOS_AJUSTE = ("sumar", "restar", "final")
MOTIVO_AJUSTE_RAPIDO = "Ajuste rápido (un producto)"


# ---------------------------------------------------------------------------
# Costo guardado al momento del movimiento
# ---------------------------------------------------------------------------
def _completar_costos(session, flush_context, instances):
    nuevos = [o for o in session.new if isinstance(o, (MovimientoInventario, DetalleVenta, OrdenRepuesto))]
    if not nuevos:
        return
    with session.no_autoflush:
        for obj in nuevos:
            if getattr(obj, "costo_unitario", None) is None and obj.producto_id:
                producto = obj.producto if obj.producto is not None else session.get(Producto, obj.producto_id)
                if producto is not None:
                    obj.costo_unitario = to_decimal(producto.costo or 0)
            if isinstance(obj, MovimientoInventario) and obj.existencia_anterior is None:
                if obj.tipo == "entrada":
                    obj.existencia_anterior = obj.existencia_resultante - (obj.cantidad or 0)
                elif obj.tipo == "salida":
                    obj.existencia_anterior = obj.existencia_resultante + (obj.cantidad or 0)


def registrar_costos_automaticos() -> None:
    if not event.contains(Session, "before_flush", _completar_costos):
        event.listen(Session, "before_flush", _completar_costos)


# ---------------------------------------------------------------------------
# Crear / revertir un ajuste
# ---------------------------------------------------------------------------
def _siguiente_numero_ajuste(db: Session) -> str:
    ultimo = db.query(AjusteInventario).order_by(AjusteInventario.id.desc()).first()
    return siguiente_numero(ultimo.numero if ultimo else None, "AJ")


def calcular_lineas(db: Session, lineas: list[dict]) -> tuple[list[dict], list[str]]:
    """Valida y calcula cada línea {producto_id, modo, cantidad} contra la
    existencia ACTUAL. No cambia nada. Devuelve (filas, errores)."""
    filas, errores, vistos = [], [], set()
    for i, linea in enumerate(lineas, start=1):
        try:
            producto_id = int(linea.get("producto_id"))
            cantidad = int(linea.get("cantidad"))
        except (TypeError, ValueError):
            errores.append(f"Línea {i}: producto o cantidad inválidos.")
            continue
        modo = linea.get("modo")
        if modo not in MODOS_AJUSTE:
            errores.append(f"Línea {i}: tipo de ajuste inválido.")
            continue
        producto = db.get(Producto, producto_id)
        if producto is None:
            errores.append(f"Línea {i}: el producto ya no existe.")
            continue
        if producto_id in vistos:
            errores.append(f"{producto.codigo} - {producto.nombre}: está repetido en el ajuste.")
            continue
        vistos.add(producto_id)
        if cantidad < 0:
            errores.append(f"{producto.codigo} - {producto.nombre}: la cantidad no puede ser negativa.")
            continue
        anterior = producto.existencia or 0
        if modo == "sumar":
            nueva = anterior + cantidad
        elif modo == "restar":
            nueva = anterior - cantidad
        else:
            nueva = cantidad
        if nueva < 0:
            errores.append(
                f"{producto.codigo} - {producto.nombre}: quedaría en {nueva} (hay {anterior}); "
                "la existencia no puede quedar negativa."
            )
            continue
        costo = to_decimal(producto.costo or 0)
        diferencia = nueva - anterior
        filas.append({
            "producto": producto, "producto_id": producto.id, "modo": modo, "cantidad": cantidad,
            "existencia_anterior": anterior, "existencia_nueva": nueva, "diferencia": diferencia,
            "costo_unitario": costo, "valor": (costo * diferencia).quantize(Decimal("0.01")),
        })
    return filas, errores


def aplicar_ajuste(
    db: Session, lineas: list[dict], motivo: str, observacion: str, origen: str,
    usuario_nombre: str, revierte_a: AjusteInventario | None = None,
) -> tuple[AjusteInventario | None, list[str]]:
    """Crea el ajuste completo o nada (si hay un error en cualquier línea no
    se aplica ninguna). Las líneas que no cambian la existencia se omiten.
    No hace commit."""
    if not (motivo or "").strip():
        return None, ["Elige el motivo del ajuste."]
    filas, errores = calcular_lineas(db, lineas)
    if errores:
        return None, errores
    cambios = [f for f in filas if f["diferencia"] != 0]
    if not cambios:
        return None, ["Ningún producto cambia de existencia con este ajuste."]

    ajuste = AjusteInventario(
        numero=_siguiente_numero_ajuste(db), fecha=datetime.utcnow(), usuario_nombre=usuario_nombre,
        motivo=motivo.strip(), observacion=(observacion or "").strip(), origen=origen,
        revierte_a_id=revierte_a.id if revierte_a else None,
    )
    db.add(ajuste)
    db.flush()

    unidades_entrada = unidades_salida = 0
    valor_entrada = valor_salida = CERO
    for f in cambios:
        producto = f["producto"]
        db.add(AjusteInventarioDetalle(
            ajuste_id=ajuste.id, producto_id=producto.id,
            producto_codigo=producto.codigo, producto_nombre=producto.nombre,
            existencia_anterior=f["existencia_anterior"], existencia_nueva=f["existencia_nueva"],
            diferencia=f["diferencia"], costo_unitario=f["costo_unitario"], valor=f["valor"],
        ))
        db.add(MovimientoInventario(
            producto_id=producto.id, tipo="ajuste", cantidad=abs(f["diferencia"]),
            existencia_anterior=f["existencia_anterior"], existencia_resultante=f["existencia_nueva"],
            costo_unitario=f["costo_unitario"], ajuste_id=ajuste.id, fecha=ajuste.fecha,
            usuario_nombre=usuario_nombre, motivo=f"Ajuste {ajuste.numero} · {ajuste.motivo}",
        ))
        producto.existencia = f["existencia_nueva"]
        if f["diferencia"] > 0:
            unidades_entrada += f["diferencia"]
            valor_entrada += f["valor"]
        else:
            unidades_salida += -f["diferencia"]
            valor_salida += -f["valor"]

    ajuste.unidades_entrada = unidades_entrada
    ajuste.unidades_salida = unidades_salida
    ajuste.valor_entrada = valor_entrada
    ajuste.valor_salida = valor_salida
    if revierte_a is not None:
        revierte_a.revertido_por_id = ajuste.id
    db.flush()
    return ajuste, []


def revertir_ajuste(db: Session, ajuste: AjusteInventario, usuario_nombre: str, nota: str = "") -> tuple[AjusteInventario | None, list[str]]:
    if ajuste.revertido_por_id:
        return None, ["Este ajuste ya fue revertido."]
    if ajuste.revierte_a_id:
        return None, ["Este ajuste es una reversión; no se puede revertir de nuevo."]
    lineas = [
        {"producto_id": d.producto_id, "modo": "restar" if d.diferencia > 0 else "sumar", "cantidad": abs(d.diferencia)}
        for d in ajuste.detalles if d.diferencia
    ]
    observacion = f"Revierte el ajuste {ajuste.numero}." + (f" {nota.strip()}" if nota.strip() else "")
    return aplicar_ajuste(db, lineas, MOTIVO_REVERSION_AJUSTE, observacion, "reversion", usuario_nombre, revierte_a=ajuste)


# ---------------------------------------------------------------------------
# Reportes (unidades y lempiras)
# ---------------------------------------------------------------------------
def reporte_ajustes(db: Session, desde: datetime | None = None, hasta: datetime | None = None,
                    motivo: str = "", q: str = "") -> dict:
    """Todos los movimientos de inventario tipo "ajuste" del rango: los de
    este módulo (con su documento AJ-) y los ajustes rápidos de un solo
    producto, incluidos los de antes del módulo. En los de antes, la
    diferencia se calcula contra el movimiento anterior del producto y el
    valor con el costo actual (se marcan como aproximados)."""
    consulta = db.query(MovimientoInventario).filter(MovimientoInventario.tipo == "ajuste")
    if desde:
        consulta = consulta.filter(MovimientoInventario.fecha >= desde)
    if hasta:
        consulta = consulta.filter(MovimientoInventario.fecha < hasta)
    movimientos = consulta.order_by(MovimientoInventario.fecha.asc(), MovimientoInventario.id.asc()).all()

    ajustes_por_id = {}
    ids = {m.ajuste_id for m in movimientos if m.ajuste_id}
    if ids:
        ajustes_por_id = {a.id: a for a in db.query(AjusteInventario).filter(AjusteInventario.id.in_(ids)).all()}

    q_norm = (q or "").strip().lower()
    filas = []
    for m in movimientos:
        producto = m.producto
        aproximado = False
        if m.existencia_anterior is not None:
            diferencia = m.existencia_resultante - m.existencia_anterior
        else:
            previo = (
                db.query(MovimientoInventario.existencia_resultante)
                .filter(
                    MovimientoInventario.producto_id == m.producto_id,
                    (MovimientoInventario.fecha < m.fecha)
                    | ((MovimientoInventario.fecha == m.fecha) & (MovimientoInventario.id < m.id)),
                )
                .order_by(MovimientoInventario.fecha.desc(), MovimientoInventario.id.desc())
                .first()
            )
            if previo is None:
                continue  # sin forma de saber cuánto cambió
            diferencia = m.existencia_resultante - previo[0]
            aproximado = True
        if diferencia == 0:
            continue
        if m.costo_unitario is not None:
            costo = to_decimal(m.costo_unitario)
        else:
            costo = to_decimal(producto.costo if producto else 0)
            aproximado = True
        ajuste = ajustes_por_id.get(m.ajuste_id) if m.ajuste_id else None
        motivo_fila = ajuste.motivo if ajuste else MOTIVO_AJUSTE_RAPIDO
        if motivo and motivo_fila != motivo:
            continue
        codigo = producto.codigo if producto else ""
        nombre = producto.nombre if producto else "(producto eliminado)"
        if q_norm and q_norm not in f"{codigo} {nombre}".lower():
            continue
        filas.append({
            "fecha": m.fecha, "ajuste": ajuste, "motivo": motivo_fila,
            "detalle_motivo": "" if ajuste else (m.motivo or ""),
            "producto_id": m.producto_id, "codigo": codigo, "nombre": nombre,
            "categoria": (producto.categoria if producto else "") or "Sin categoría",
            "diferencia": diferencia, "costo_unitario": costo,
            "valor": (costo * diferencia).quantize(Decimal("0.01")),
            "usuario": m.usuario_nombre or "", "aproximado": aproximado,
        })

    def _acumular(clave_fn):
        grupos = OrderedDict()
        for f in filas:
            clave = clave_fn(f)
            g = grupos.setdefault(clave, {"clave": clave, "unidades_entrada": 0, "unidades_salida": 0,
                                         "valor_entrada": CERO, "valor_salida": CERO, "lineas": 0})
            g["lineas"] += 1
            if f["diferencia"] > 0:
                g["unidades_entrada"] += f["diferencia"]
                g["valor_entrada"] += f["valor"]
            else:
                g["unidades_salida"] += -f["diferencia"]
                g["valor_salida"] += -f["valor"]
        for g in grupos.values():
            g["valor_neto"] = g["valor_entrada"] - g["valor_salida"]
            g["unidades_neto"] = g["unidades_entrada"] - g["unidades_salida"]
        return list(grupos.values())

    total = _acumular(lambda f: "total")
    por_producto = sorted(_acumular(lambda f: f"{f['codigo']} - {f['nombre']}"), key=lambda g: g["valor_neto"])
    return {
        "filas": list(reversed(filas)),
        "total": total[0] if total else {"unidades_entrada": 0, "unidades_salida": 0, "valor_entrada": CERO,
                                          "valor_salida": CERO, "valor_neto": CERO, "unidades_neto": 0, "lineas": 0},
        "por_motivo": sorted(_acumular(lambda f: f["motivo"]), key=lambda g: g["valor_neto"]),
        "por_producto": por_producto,
        "por_categoria": sorted(_acumular(lambda f: f["categoria"]), key=lambda g: g["valor_neto"]),
        "por_mes": _acumular(lambda f: a_hora_local(f["fecha"]).strftime("%Y-%m")),
        "hay_aproximados": any(f["aproximado"] for f in filas),
    }
