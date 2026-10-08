"""Módulo de reportes con filtros y exportación a CSV y Excel.

El estilo de los Excel (encabezado con el nombre del taller, fila de
títulos con fondo azul, columnas ajustadas, fila de totales) está basado
en el reporte de referencia que compartió el usuario ("Reporte de Ventas
Pedidos Detallado")."""
import csv
import io
from datetime import datetime, date
from decimal import Decimal

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.templates_env import templates
from app.database import get_db
from app.models import (
    OrdenServicio, MovimientoFinanciero, Venta, DetalleVenta, Producto, Tecnico, Configuracion,
    ConfiguracionFacturacion, ESTADOS_ORDEN, FORMAS_PAGO, Servicio, OrdenServicioExtra,
    CATEGORIA_DEPOSITO_BANCO,
)
from app.utils.calculations import to_decimal
from app.utils.flash import flash
from app.utils.caja_calculos import CUENTA_CAJA_CHICA, CUENTA_BANCO
from app.deps import login_required

router = APIRouter()

MESES_ABREV = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

# Cuántas filas se muestran en pantalla en el reporte de Ventas detallado
# (que puede tener miles de filas si no se filtra por fecha). El Excel y
# el CSV siempre llevan TODAS las filas, sin este límite.
MAX_FILAS_PANTALLA_DETALLADO = 300


def _isv_tasa(db: Session) -> Decimal:
    cfg = db.get(ConfiguracionFacturacion, 1)
    if cfg and cfg.isv_tasa is not None:
        return to_decimal(cfg.isv_tasa)
    return to_decimal(15)


def _nombre_taller(db: Session) -> str:
    cfg = db.get(Configuracion, 1)
    return (cfg.nombre_taller if cfg and cfg.nombre_taller else "Mi Taller")


def _utilidades_por_producto(db: Session, fecha_desde=None, fecha_hasta=None):
    """Utilidad generada por cada producto vendido (POS y repuestos usados
    en órdenes, que también quedan como Venta/DetalleVenta): ingresos menos
    costo, usando el costo ACTUAL del producto en Inventario (no se guarda
    un historial de costo por venta). Ordenado de mayor a menor utilidad."""
    q = (
        db.query(
            Producto.id, Producto.codigo, Producto.nombre, Producto.costo, Producto.precio_venta,
            func.coalesce(func.sum(DetalleVenta.cantidad), 0),
            func.coalesce(func.sum(DetalleVenta.subtotal), 0),
        )
        .join(DetalleVenta, DetalleVenta.producto_id == Producto.id)
        .join(Venta, Venta.id == DetalleVenta.venta_id)
    )
    if fecha_desde:
        q = q.filter(Venta.fecha >= fecha_desde)
    if fecha_hasta:
        q = q.filter(Venta.fecha <= fecha_hasta)
    q = q.group_by(Producto.id, Producto.codigo, Producto.nombre, Producto.costo, Producto.precio_venta)

    resultado = []
    for producto_id, codigo, nombre, costo, precio_venta, unidades, ingresos in q.all():
        costo = to_decimal(costo)
        ingresos = to_decimal(ingresos)
        costo_total = (costo * unidades).quantize(Decimal("0.01"))
        utilidad = (ingresos - costo_total).quantize(Decimal("0.01"))
        margen_pct = float((utilidad / ingresos * 100).quantize(Decimal("0.1"))) if ingresos > 0 else 0.0
        resultado.append({
            "producto_id": producto_id, "codigo": codigo, "nombre": nombre,
            "unidades": unidades, "costo_unitario": costo, "precio_unitario": to_decimal(precio_venta),
            "ingresos": ingresos, "costo_total": costo_total, "utilidad": utilidad, "margen_pct": margen_pct,
        })
    resultado.sort(key=lambda r: r["utilidad"], reverse=True)
    return resultado


def _utilidades_por_servicio(db: Session, fecha_desde=None, fecha_hasta=None):
    """Utilidad generada por cada servicio del catálogo agregado a alguna
    orden: ingresos menos costo, usando el costo que se guardó al momento
    de agregar el servicio a la orden (no el costo actual del catálogo, por
    si cambió después de esa fecha). Un servicio sin costo asociado cuenta
    como costo cero (utilidad = 100% del precio). Ordenado de mayor a menor
    utilidad."""
    q = (
        db.query(
            Servicio.id, Servicio.nombre, Servicio.categoria,
            func.coalesce(func.sum(OrdenServicioExtra.cantidad), 0),
            func.coalesce(func.sum(OrdenServicioExtra.subtotal), 0),
            func.coalesce(func.sum(OrdenServicioExtra.costo_unitario * OrdenServicioExtra.cantidad), 0),
        )
        .join(OrdenServicioExtra, OrdenServicioExtra.servicio_id == Servicio.id)
    )
    if fecha_desde:
        q = q.filter(OrdenServicioExtra.fecha >= fecha_desde)
    if fecha_hasta:
        q = q.filter(OrdenServicioExtra.fecha <= fecha_hasta)
    q = q.group_by(Servicio.id, Servicio.nombre, Servicio.categoria)

    resultado = []
    for servicio_id, nombre, categoria, unidades, ingresos, costo_total in q.all():
        ingresos = to_decimal(ingresos)
        costo_total = to_decimal(costo_total).quantize(Decimal("0.01"))
        utilidad = (ingresos - costo_total).quantize(Decimal("0.01"))
        margen_pct = float((utilidad / ingresos * 100).quantize(Decimal("0.1"))) if ingresos > 0 else 0.0
        resultado.append({
            "servicio_id": servicio_id, "nombre": nombre, "categoria": categoria or "-",
            "unidades": unidades, "ingresos": ingresos, "costo_total": costo_total,
            "utilidad": utilidad, "margen_pct": margen_pct,
        })
    resultado.sort(key=lambda r: r["utilidad"], reverse=True)
    return resultado


def _ventas_detallado(db: Session, fecha_desde=None, fecha_hasta=None):
    """Detalle línea por línea de cada producto vendido (POS y repuestos
    usados en órdenes): cliente, técnico/vendedor, factura, cantidad,
    precio, exento/gravado/ISV, monto, costo y utilidad de esa línea. Es el
    equivalente al "Reporte de Ventas Pedidos Detallado" que se usaba antes.

    La columna Técnico muestra quién REPARÓ (orden.tecnico_reparacion), que
    no siempre es el mismo que recibió el equipo; si esa venta no viene de
    una orden con reparación asignada, se usa como respaldo el técnico que
    recibió la orden y, si tampoco hay orden, el usuario que hizo la venta
    en el Punto de Venta.

    Igual que en Utilidades por producto: el costo es el ACTUAL del
    producto en Inventario (no hay historial de costo por venta), y el
    ISV se calcula línea por línea sobre el subtotal de esa línea (no se
    reparte proporcionalmente el descuento de la venta, si tuvo uno)."""
    tasa = _isv_tasa(db)
    q = (
        db.query(DetalleVenta, Venta, Producto)
        .join(Venta, Venta.id == DetalleVenta.venta_id)
        .join(Producto, Producto.id == DetalleVenta.producto_id)
        .options(
            joinedload(Venta.cliente),
            joinedload(Venta.orden).joinedload(OrdenServicio.tecnico_reparacion),
            joinedload(Venta.orden).joinedload(OrdenServicio.tecnico),
        )
    )
    if fecha_desde:
        q = q.filter(Venta.fecha >= fecha_desde)
    if fecha_hasta:
        q = q.filter(Venta.fecha <= fecha_hasta)
    q = q.order_by(Venta.fecha.asc(), Venta.id.asc(), DetalleVenta.id.asc())

    filas = []
    for idx, (detalle, venta, producto) in enumerate(q.all(), start=1):
        cantidad = detalle.cantidad
        precio = to_decimal(detalle.precio_unitario)
        gravado = to_decimal(detalle.subtotal)
        isv = (gravado * tasa / Decimal(100)).quantize(Decimal("0.01"))
        monto = (gravado + isv).quantize(Decimal("0.01"))
        costo_total = (to_decimal(producto.costo) * cantidad).quantize(Decimal("0.01"))
        utilidad = (gravado - costo_total).quantize(Decimal("0.01"))
        margen = float((utilidad / gravado * 100).quantize(Decimal("0.1"))) if gravado > 0 else 0.0

        tecnico = None
        if venta.orden and venta.orden.tecnico_reparacion:
            tecnico = venta.orden.tecnico_reparacion.nombre
        elif venta.orden and venta.orden.tecnico:
            tecnico = venta.orden.tecnico.nombre
        elif venta.usuario_nombre:
            tecnico = venta.usuario_nombre

        cliente = venta.cliente
        filas.append([
            idx, venta.fecha.strftime("%Y-%m-%d"),
            f"CLI-{cliente.id}" if cliente else "-",
            cliente.nombre if cliente else "Consumidor final",
            tecnico or "-", venta.numero_venta, cantidad, float(precio),
            producto.codigo, producto.nombre,
            0.0, float(gravado), float(isv), float(monto), float(costo_total), float(utilidad),
            f"{margen:.2f}%",
        ])
    return filas


ENCABEZADOS_VENTAS_DETALLADO = [
    "#", "Fecha", "Codigo Cliente", "Cliente", "Técnico", "Factura", "Cantidad", "Precio",
    "Código Producto", "Nombre Producto", "Exento", "Gravado", "Isv", "Monto",
    "Costo Producto", "Utilidad", "Promedio %",
]
# Columnas (0-indexado, según ENCABEZADOS_VENTAS_DETALLADO) que se suman en
# la fila de totales: Cantidad, Exento, Gravado, Isv, Monto, Costo, Utilidad.
# Se excluyen Precio (es un valor unitario) y Promedio % (es un porcentaje).
COLUMNAS_TOTALES_VENTAS_DETALLADO = [6, 10, 11, 12, 13, 14, 15]


def _parse_fecha(valor, default=None):
    if not valor:
        return default
    try:
        return datetime.strptime(valor, "%Y-%m-%d")
    except ValueError:
        return default


def _filtrar_ordenes(db, desde, hasta, tecnico_id, estado):
    query = db.query(OrdenServicio).options(joinedload(OrdenServicio.cliente), joinedload(OrdenServicio.tecnico))
    if desde:
        query = query.filter(OrdenServicio.fecha >= desde)
    if hasta:
        query = query.filter(OrdenServicio.fecha <= hasta)
    if tecnico_id:
        query = query.filter(OrdenServicio.tecnico_id == int(tecnico_id))
    if estado:
        query = query.filter(OrdenServicio.estado == estado)
    return query.order_by(OrdenServicio.fecha.desc()).all()


@router.get("/reportes")
def reportes_index(
    request: Request, tipo: str = "ordenes",
    desde: str = "", hasta: str = "", tecnico_id: str = "", estado: str = "", forma_pago: str = "",
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    fecha_desde = _parse_fecha(desde)
    fecha_hasta = _parse_fecha(hasta)
    if fecha_hasta:
        fecha_hasta = fecha_hasta.replace(hour=23, minute=59, second=59)

    contexto = {
        "request": request, "usuario": usuario, "tipo": tipo,
        "desde": desde, "hasta": hasta, "tecnico_id": tecnico_id, "estado": estado, "forma_pago": forma_pago,
        "tecnicos": db.query(Tecnico).order_by(Tecnico.nombre).all(),
        "estados": ESTADOS_ORDEN, "formas_pago": FORMAS_PAGO,
    }

    if tipo == "ordenes" or tipo == "reparaciones":
        contexto["ordenes"] = _filtrar_ordenes(db, fecha_desde, fecha_hasta, tecnico_id, estado)
    elif tipo == "ingresos":
        # Un Depósito Bancario (traslado de Caja Chica a Banco) se excluye:
        # no es un ingreso real, es el mismo dinero cambiando de cuenta.
        q = db.query(MovimientoFinanciero).filter(
            MovimientoFinanciero.tipo == "ingreso", MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
            MovimientoFinanciero.categoria != CATEGORIA_DEPOSITO_BANCO,
        )
        if fecha_desde:
            q = q.filter(MovimientoFinanciero.fecha >= fecha_desde)
        if fecha_hasta:
            q = q.filter(MovimientoFinanciero.fecha <= fecha_hasta)
        contexto["movimientos"] = q.order_by(MovimientoFinanciero.fecha.desc()).all()
    elif tipo == "gastos":
        # Mismo caso: el lado de Caja Chica de un Depósito Bancario no es un
        # gasto real, es un traslado hacia Banco (ver /caja/conciliacion).
        q = db.query(MovimientoFinanciero).filter(
            MovimientoFinanciero.tipo == "gasto", MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
            MovimientoFinanciero.categoria != CATEGORIA_DEPOSITO_BANCO,
        )
        if fecha_desde:
            q = q.filter(MovimientoFinanciero.fecha >= fecha_desde)
        if fecha_hasta:
            q = q.filter(MovimientoFinanciero.fecha <= fecha_hasta)
        contexto["movimientos"] = q.order_by(MovimientoFinanciero.fecha.desc()).all()
    elif tipo == "ventas":
        q = db.query(Venta)
        if fecha_desde:
            q = q.filter(Venta.fecha >= fecha_desde)
        if fecha_hasta:
            q = q.filter(Venta.fecha <= fecha_hasta)
        if forma_pago:
            q = q.filter(Venta.forma_pago == forma_pago)
        contexto["ventas"] = q.order_by(Venta.fecha.desc()).all()
    elif tipo == "inventario":
        contexto["productos"] = db.query(Producto).order_by(Producto.nombre).all()
    elif tipo == "saldos":
        contexto["ordenes"] = db.query(OrdenServicio).options(joinedload(OrdenServicio.cliente)).filter(
            OrdenServicio.saldo > 0, OrdenServicio.estado != "CANCELADO"
        ).order_by(OrdenServicio.fecha.desc()).all()
    elif tipo == "utilidades":
        contexto["utilidades"] = _utilidades_por_producto(db, fecha_desde, fecha_hasta)
    elif tipo == "utilidad_servicios":
        contexto["utilidad_servicios"] = _utilidades_por_servicio(db, fecha_desde, fecha_hasta)
    elif tipo == "ventas_detallado":
        filas = _ventas_detallado(db, fecha_desde, fecha_hasta)
        truncado = len(filas) > MAX_FILAS_PANTALLA_DETALLADO
        # Si hay que recortar la vista en pantalla, se muestran las
        # transacciones MÁS RECIENTES (las filas ya vienen ordenadas de más
        # antigua a más reciente), no las más antiguas. El Excel y el CSV
        # siempre llevan todas las filas, sin este límite.
        contexto["detalle_ventas"] = filas[-MAX_FILAS_PANTALLA_DETALLADO:] if truncado else filas
        contexto["detalle_ventas_total_filas"] = len(filas)
        contexto["detalle_ventas_truncado"] = truncado

    return templates.TemplateResponse("reportes/index.html", contexto)


def _csv_response(filas, encabezados, nombre_archivo):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(encabezados)
    writer.writerows(filas)
    buffer.seek(0)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv",
                              headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'})


def _fecha_corta(dt) -> str:
    return f"{dt.day:02d} {MESES_ABREV[dt.month - 1]} {dt.year}"


def _rango_fechas_texto(fecha_desde, fecha_hasta) -> str:
    if fecha_desde and fecha_hasta:
        return f"Fecha: {_fecha_corta(fecha_desde)} al {_fecha_corta(fecha_hasta)}"
    if fecha_desde:
        return f"Fecha: desde el {_fecha_corta(fecha_desde)}"
    if fecha_hasta:
        return f"Fecha: hasta el {_fecha_corta(fecha_hasta)}"
    return "Fecha: todas las fechas"


def _xlsx_response(filas, encabezados, nombre_archivo, titulo_hoja="Reporte",
                    titulo_reporte=None, subtitulo=None, nombre_taller=None, columnas_totales=None):
    """Genera un Excel (.xlsx) con el mismo estilo en todos los reportes del
    sistema, basado en el reporte de referencia del usuario: encabezado con
    el nombre del taller + título del reporte + rango de fechas, fila de
    títulos con fondo azul y bordes, columnas ajustadas al contenido, fila
    de encabezado congelada y una fila de TOTAL al final (cuando aplica)."""
    wb = Workbook()
    hoja = wb.active
    hoja.title = titulo_hoja[:31] or "Reporte"
    n_col = max(len(encabezados), 1)

    fuente_titulo = Font(name="Calibri", size=14, bold=True)
    textos_titulo = [nombre_taller or "Mi Taller", titulo_reporte or titulo_hoja, subtitulo or ""]
    for fila_idx, texto in enumerate(textos_titulo, start=1):
        hoja.merge_cells(start_row=fila_idx, start_column=1, end_row=fila_idx, end_column=n_col)
        celda = hoja.cell(row=fila_idx, column=1, value=texto)
        celda.font = fuente_titulo
        celda.alignment = Alignment(horizontal="center")

    fila_encabezado = 5
    encabezado_fill = PatternFill(start_color="3D5F96", end_color="3D5F96", fill_type="solid")
    encabezado_font = Font(bold=True, color="000000")
    borde_fino = Border(left=Side(style="thin"), right=Side(style="thin"),
                         top=Side(style="thin"), bottom=Side(style="thin"))
    for col, titulo in enumerate(encabezados, start=1):
        celda = hoja.cell(row=fila_encabezado, column=col, value=titulo)
        celda.fill = encabezado_fill
        celda.font = encabezado_font
        celda.alignment = Alignment(vertical="center")
        celda.border = borde_fino

    for i, fila in enumerate(filas):
        fila_idx = fila_encabezado + 1 + i
        for col_idx, valor in enumerate(fila, start=1):
            celda = hoja.cell(row=fila_idx, column=col_idx, value=valor)
            if isinstance(valor, float):
                celda.number_format = "#,##0.00"

    ultima_fila_datos = fila_encabezado + len(filas)

    if filas and columnas_totales:
        fila_total = ultima_fila_datos + 1
        primera_num = min(columnas_totales)
        if primera_num > 1:
            hoja.merge_cells(start_row=fila_total, start_column=1, end_row=fila_total, end_column=primera_num)
        celda_label = hoja.cell(row=fila_total, column=1, value="TOTAL")
        celda_label.font = Font(bold=True)
        celda_label.alignment = Alignment(horizontal="right")
        for c in columnas_totales:
            suma = sum(f[c] for f in filas if c < len(f) and isinstance(f[c], (int, float)))
            celda = hoja.cell(row=fila_total, column=c + 1, value=suma)
            celda.font = Font(bold=True)
            celda.number_format = "#,##0.00"

    for col_idx, titulo in enumerate(encabezados, start=1):
        largo = len(str(titulo))
        for fila in filas[:300]:
            if col_idx - 1 < len(fila):
                largo = max(largo, len(str(fila[col_idx - 1])))
        hoja.column_dimensions[get_column_letter(col_idx)].width = min(max(largo + 2, 10), 40)

    hoja.freeze_panes = f"A{fila_encabezado + 1}"
    ultima_col_letra = get_column_letter(n_col)
    hoja.auto_filter.ref = f"A{fila_encabezado}:{ultima_col_letra}{ultima_fila_datos if filas else fila_encabezado}"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


def _datos_reporte(tipo, fecha_desde, fecha_hasta, tecnico_id, estado, db):
    """Arma las filas y encabezados de un reporte, en el mismo formato
    para CSV y para Excel. Devuelve (filas, encabezados, nombre_base,
    titulo_hoja, columnas_totales) — columnas_totales es la lista de
    columnas (0-indexado) que se suman en la fila de TOTAL del Excel."""
    if tipo in ("ordenes", "reparaciones"):
        ordenes = _filtrar_ordenes(db, fecha_desde, fecha_hasta, tecnico_id, estado)
        filas = [[o.numero_orden, o.fecha.strftime("%d/%m/%Y"), o.cliente.nombre if o.cliente else "",
                  o.tipo_equipo, o.marca, o.modelo, o.estado, o.tecnico.nombre if o.tecnico else "",
                  float(o.total), float(o.abonado), float(o.saldo)] for o in ordenes]
        return (filas, ["N. Orden", "Fecha", "Cliente", "Tipo", "Marca", "Modelo", "Estado", "Tecnico", "Total", "Abonado", "Saldo"],
                "reporte_ordenes", "Ordenes", [8, 9, 10])

    if tipo in ("ingresos", "gastos"):
        q = db.query(MovimientoFinanciero).filter(
            MovimientoFinanciero.tipo == ("ingreso" if tipo == "ingresos" else "gasto"),
            MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
            # Depósito Bancario es un traslado de Caja Chica a Banco, no un
            # ingreso/gasto real — se excluye también en este export.
            MovimientoFinanciero.categoria != CATEGORIA_DEPOSITO_BANCO,
        )
        if fecha_desde:
            q = q.filter(MovimientoFinanciero.fecha >= fecha_desde)
        if fecha_hasta:
            q = q.filter(MovimientoFinanciero.fecha <= fecha_hasta)
        movimientos = q.order_by(MovimientoFinanciero.fecha.desc()).all()
        if tipo == "gastos":
            # En Egresos la última columna es cómo salió el dinero
            # (Efectivo/Transferencia/Tarjeta/Otro) en vez de la Referencia
            # interna, que no le dice nada al usuario.
            filas = [[m.fecha.strftime("%d/%m/%Y %H:%M"), m.categoria, float(m.monto), m.descripcion,
                      m.metodo_pago or ""] for m in movimientos]
            return (filas, ["Fecha", "Categoria", "Monto", "Descripcion", "Metodo de pago"], "reporte_gastos",
                    "Egresos", [2])
        filas = [[m.fecha.strftime("%d/%m/%Y %H:%M"), m.categoria, float(m.monto), m.descripcion, m.referencia] for m in movimientos]
        return (filas, ["Fecha", "Categoria", "Monto", "Descripcion", "Referencia"], f"reporte_{tipo}",
                "Ingresos", [2])

    if tipo == "ventas":
        ventas = db.query(Venta).order_by(Venta.fecha.desc()).all()
        filas = [[v.numero_venta, v.fecha.strftime("%d/%m/%Y %H:%M"), float(v.subtotal), float(v.descuento),
                  float(v.total), v.forma_pago] for v in ventas]
        return (filas, ["N. Venta", "Fecha", "Subtotal", "Descuento", "Total", "Forma de pago"],
                "reporte_ventas", "Ventas", [2, 3, 4])

    if tipo == "ventas_detallado":
        filas = _ventas_detallado(db, fecha_desde, fecha_hasta)
        return (filas, ENCABEZADOS_VENTAS_DETALLADO, "reporte_ventas_detallado", "Ventas Detallado",
                COLUMNAS_TOTALES_VENTAS_DETALLADO)

    if tipo == "inventario":
        productos = db.query(Producto).order_by(Producto.nombre).all()
        filas = [[p.codigo, p.nombre, p.categoria, p.marca, p.caja, float(p.costo), float(p.precio_venta),
                  p.existencia, p.stock_minimo] for p in productos]
        return (filas, ["Codigo", "Nombre", "Categoria", "Marca", "Caja", "Costo", "Precio", "Existencia", "Stock minimo"],
                "reporte_inventario", "Inventario", [7, 8])

    if tipo == "utilidad_servicios":
        utilidad_servicios = _utilidades_por_servicio(db, fecha_desde, fecha_hasta)
        filas = [[u["nombre"], u["categoria"], u["unidades"], float(u["ingresos"]),
                  float(u["costo_total"]), float(u["utilidad"]), f"{u['margen_pct']:.2f}%"] for u in utilidad_servicios]
        return (filas, ["Servicio", "Categoria", "Unidades agregadas", "Ingresos", "Costo total", "Utilidad", "Margen %"],
                "reporte_utilidad_servicios", "Utilidad de Servicios", [2, 3, 4, 5])

    if tipo == "saldos":
        ordenes = db.query(OrdenServicio).options(joinedload(OrdenServicio.cliente)).filter(
            OrdenServicio.saldo > 0, OrdenServicio.estado != "CANCELADO"
        ).order_by(OrdenServicio.fecha.desc()).all()
        filas = [[o.numero_orden, o.cliente.nombre if o.cliente else "", float(o.total), float(o.abonado), float(o.saldo)] for o in ordenes]
        return (filas, ["N. Orden", "Cliente", "Total", "Abonado", "Saldo"], "reporte_saldos", "Saldos", [2, 3, 4])

    if tipo == "utilidades":
        utilidades = _utilidades_por_producto(db, fecha_desde, fecha_hasta)
        filas = [[u["codigo"], u["nombre"], u["unidades"], float(u["costo_unitario"]), float(u["precio_unitario"]),
                  float(u["ingresos"]), float(u["costo_total"]), float(u["utilidad"]), f"{u['margen_pct']:.2f}%"] for u in utilidades]
        return (filas, ["Codigo", "Nombre", "Unidades vendidas", "Costo unitario", "Precio unitario",
                        "Ingresos", "Costo total", "Utilidad", "Margen %"],
                "reporte_utilidades", "Utilidades", [2, 5, 6, 7])

    return [], ["Sin datos"], "reporte", "Reporte", None


TITULOS_REPORTE = {
    "ordenes": "Reporte de Órdenes", "reparaciones": "Reporte de Órdenes",
    "ingresos": "Reporte de Ingresos", "gastos": "Reporte de Egresos",
    "ventas": "Reporte de Ventas", "ventas_detallado": "Reporte de Ventas Detallado",
    "inventario": "Reporte de Inventario", "saldos": "Reporte de Saldos Pendientes",
    "utilidades": "Reporte de Utilidades por Producto",
    "utilidad_servicios": "Reporte de Utilidad de Servicios",
}


def _rango_fechas(desde, hasta):
    fecha_desde = _parse_fecha(desde)
    fecha_hasta = _parse_fecha(hasta)
    if fecha_hasta:
        fecha_hasta = fecha_hasta.replace(hour=23, minute=59, second=59)
    return fecha_desde, fecha_hasta


@router.get("/reportes/exportar/{tipo}")
def reportes_exportar_csv(
    tipo: str, desde: str = "", hasta: str = "", tecnico_id: str = "", estado: str = "", forma_pago: str = "",
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    fecha_desde, fecha_hasta = _rango_fechas(desde, hasta)
    filas, encabezados, nombre_base, _, _ = _datos_reporte(tipo, fecha_desde, fecha_hasta, tecnico_id, estado, db)
    return _csv_response(filas, encabezados, f"{nombre_base}.csv")


@router.get("/reportes/exportar/{tipo}/excel")
def reportes_exportar_excel(
    tipo: str, desde: str = "", hasta: str = "", tecnico_id: str = "", estado: str = "", forma_pago: str = "",
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    fecha_desde, fecha_hasta = _rango_fechas(desde, hasta)
    filas, encabezados, nombre_base, titulo_hoja, columnas_totales = _datos_reporte(
        tipo, fecha_desde, fecha_hasta, tecnico_id, estado, db
    )
    return _xlsx_response(
        filas, encabezados, f"{nombre_base}.xlsx", titulo_hoja,
        titulo_reporte=TITULOS_REPORTE.get(tipo, titulo_hoja),
        subtitulo=_rango_fechas_texto(fecha_desde, fecha_hasta),
        nombre_taller=_nombre_taller(db),
        columnas_totales=columnas_totales,
    )


@router.post("/reportes/movimiento")
def reportes_registrar_movimiento(
    request: Request,
    tipo: str = Form(...), categoria: str = Form(...), monto: str = Form(...), descripcion: str = Form(""),
    metodo_pago: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    """Registra un ingreso o gasto manual (por ejemplo el pago de un
    servicio, una compra de insumos, un retiro de caja): para que cualquiera
    que use el sistema (no solo lo que genera automáticamente una venta o
    un pago de orden) pueda dejarlo anotado en Ingresos/Egresos."""
    if tipo not in ("ingreso", "gasto"):
        flash(request, "Tipo de movimiento no válido.", "error")
        return RedirectResponse("/reportes?tipo=ingresos", status_code=303)

    categoria_limpia = categoria.strip()
    if not categoria_limpia:
        flash(request, "La categoría es obligatoria.", "error")
        return RedirectResponse(f"/reportes?tipo={'ingresos' if tipo == 'ingreso' else 'gastos'}", status_code=303)

    monto_decimal = to_decimal(monto)
    if monto_decimal <= 0:
        flash(request, "El monto debe ser mayor a cero.", "error")
        return RedirectResponse(f"/reportes?tipo={'ingresos' if tipo == 'ingreso' else 'gastos'}", status_code=303)

    # La "Forma de pago" solo aplica a un Egreso (de dónde salió el
    # dinero: efectivo, transferencia, tarjeta...); en un Ingreso se deja
    # vacío. Si se registra sin elegirla, queda pendiente y se puede
    # completar después desde la tabla (ver reportes_actualizar_forma_pago).
    metodo_pago_limpio = metodo_pago.strip() if tipo == "gasto" and metodo_pago.strip() in FORMAS_PAGO else None

    # Efectivo (o sin elegir todavía) -> Caja Chica; Transferencia/Tarjeta/
    # Otro -> Banco, porque ese dinero nunca pasó físicamente por la caja.
    cuenta_mov = CUENTA_BANCO if metodo_pago_limpio in ("Transferencia", "Tarjeta", "Otro") else CUENTA_CAJA_CHICA

    db.add(MovimientoFinanciero(
        tipo=tipo, categoria=categoria_limpia, monto=monto_decimal.quantize(Decimal("0.01")),
        descripcion=descripcion.strip(), usuario_nombre=usuario["nombre_completo"],
        referencia="Manual", metodo_pago=metodo_pago_limpio, cuenta=cuenta_mov,
    ))
    db.commit()
    flash(request, ("Ingreso" if tipo == "ingreso" else "Egreso") + " registrado correctamente.", "success")
    return RedirectResponse(f"/reportes?tipo={'ingresos' if tipo == 'ingreso' else 'gastos'}", status_code=303)


@router.post("/reportes/movimiento/{movimiento_id}/forma-pago")
def reportes_actualizar_forma_pago(
    movimiento_id: int, request: Request, metodo_pago: str = Form(""),
    desde: str = Form(""), hasta: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    """Elección rápida desde la misma tabla de Egresos: para cuando se
    registró un egreso sin la forma de pago (por ejemplo la Cajera no lo
    supo en el momento), cualquiera que use el sistema lo puede completar
    o corregir después sin tener que editar el movimiento completo. No
    afecta el monto, pero SÍ reclasifica la cuenta (Caja Chica/Banco) para
    que coincida con la forma de pago elegida -- ver la misma regla en
    reportes_registrar_movimiento."""
    mov = db.get(MovimientoFinanciero, movimiento_id)
    destino = f"/reportes?tipo=gastos&desde={desde}&hasta={hasta}"
    if not mov or mov.tipo != "gasto":
        flash(request, "Egreso no encontrado.", "error")
        return RedirectResponse(destino, status_code=303)

    valor = metodo_pago.strip()
    mov.metodo_pago = valor if valor in FORMAS_PAGO else None
    mov.cuenta = CUENTA_BANCO if mov.metodo_pago in ("Transferencia", "Tarjeta", "Otro") else CUENTA_CAJA_CHICA
    db.commit()
    flash(request, "Forma de pago actualizada.", "success")
    return RedirectResponse(destino, status_code=303)
