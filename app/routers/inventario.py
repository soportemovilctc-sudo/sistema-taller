"""Módulo de inventario: productos, entradas, salidas, ajustes y alertas de stock."""
import io
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment

from app.templates_env import templates
from app.database import get_db
from app.models import Producto, MovimientoInventario, ConfiguracionFacturacion
from app.utils.calculations import to_decimal
from app.utils.flash import flash
from app.deps import login_required, roles_required

router = APIRouter()

# Columnas de la plantilla de carga masiva, en este orden exacto.
COLUMNAS_PLANTILLA = [
    "Código", "Nombre", "Categoría", "Marca", "Costo",
    "Precio de venta", "Existencia", "Stock mínimo", "Proveedor", "Caja",
]


def _isv_tasa(db: Session):
    """Tasa de ISV configurada en Configuración > Facturación (15% si aún
    no se ha configurado nada)."""
    cfg = db.get(ConfiguracionFacturacion, 1)
    if cfg and cfg.isv_tasa is not None:
        return to_decimal(cfg.isv_tasa)
    return to_decimal(15)


def _quitar_impuesto(valor, tasa):
    """Devuelve el valor SIN el impuesto, para cuando el usuario escribe un
    número redondo que YA incluye el impuesto y quiere que el sistema le
    reste esa parte automáticamente (misma fórmula que usa facturación para
    sacar el importe gravado de un total con impuesto incluido)."""
    return (to_decimal(valor) / (1 + to_decimal(tasa) / to_decimal(100))).quantize(to_decimal("0.01"))


@router.get("/inventario")
def inventario_list(request: Request, q: str = "", db: Session = Depends(get_db), usuario=Depends(login_required)):
    query = db.query(Producto)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Producto.codigo.ilike(like), Producto.nombre.ilike(like),
                                  Producto.categoria.ilike(like), Producto.marca.ilike(like)))
    productos = query.order_by(Producto.nombre).all()
    stock_bajo_ids = {p.id for p in productos if p.existencia <= p.stock_minimo}
    return templates.TemplateResponse("inventario/list.html", {
        "request": request, "productos": productos, "q": q, "usuario": usuario, "stock_bajo_ids": stock_bajo_ids,
    })


@router.get("/inventario/precios")
def inventario_precios(request: Request, q: str = "", db: Session = Depends(get_db), usuario=Depends(login_required)):
    """Vista de solo lectura que muestra, junto al Costo y Precio de venta
    normales (sin impuesto, tal como se guardan), el mismo valor con el
    impuesto ya sumado — para no tener que calcularlo a mano cada vez. No
    modifica ni guarda nada."""
    query = db.query(Producto)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Producto.codigo.ilike(like), Producto.nombre.ilike(like),
                                  Producto.categoria.ilike(like), Producto.marca.ilike(like)))
    productos = query.order_by(Producto.nombre).all()
    tasa = _isv_tasa(db)
    factor = 1 + tasa / to_decimal(100)
    filas = [
        {
            "producto": p,
            "costo_con_impuesto": (to_decimal(p.costo) * factor).quantize(to_decimal("0.01")),
            "precio_con_impuesto": (to_decimal(p.precio_venta) * factor).quantize(to_decimal("0.01")),
        }
        for p in productos
    ]
    return templates.TemplateResponse("inventario/precios.html", {
        "request": request, "filas": filas, "q": q, "usuario": usuario, "tasa": tasa,
    })


@router.get("/inventario/nuevo")
def inventario_nuevo_form(request: Request, usuario=Depends(login_required)):
    return templates.TemplateResponse("inventario/form.html", {"request": request, "producto": None, "usuario": usuario})


@router.post("/inventario/nuevo")
def inventario_crear(
    request: Request,
    codigo: str = Form(...), nombre: str = Form(...), categoria: str = Form(""), marca: str = Form(""),
    costo: str = Form("0"), precio_venta: str = Form("0"), existencia: int = Form(0),
    stock_minimo: int = Form(0), proveedor: str = Form(""), caja: str = Form(""),
    precios_incluyen_impuesto: bool = Form(False),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    existe = db.query(Producto).filter(Producto.codigo == codigo.strip()).first()
    if existe:
        flash(request, "Ya existe un producto con ese código.", "error")
        return RedirectResponse("/inventario/nuevo", status_code=303)
    costo_final = to_decimal(costo)
    precio_final = to_decimal(precio_venta)
    if precios_incluyen_impuesto:
        tasa = _isv_tasa(db)
        costo_final = _quitar_impuesto(costo_final, tasa)
        precio_final = _quitar_impuesto(precio_final, tasa)
    producto = Producto(
        codigo=codigo.strip(), nombre=nombre.strip(), categoria=categoria, marca=marca,
        costo=costo_final, precio_venta=precio_final,
        existencia=max(0, existencia), stock_minimo=max(0, stock_minimo), proveedor=proveedor,
        caja=caja.strip(), estado="activo",
    )
    db.add(producto)
    db.commit()
    flash(request, "Producto creado correctamente.", "success")
    return RedirectResponse("/inventario", status_code=303)


@router.get("/inventario/{producto_id}/editar")
def inventario_editar_form(producto_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    producto = db.get(Producto, producto_id)
    if not producto:
        flash(request, "Producto no encontrado.", "error")
        return RedirectResponse("/inventario", status_code=303)
    return templates.TemplateResponse("inventario/form.html", {"request": request, "producto": producto, "usuario": usuario})


@router.post("/inventario/{producto_id}/editar")
def inventario_actualizar(
    producto_id: int, request: Request,
    nombre: str = Form(...), categoria: str = Form(""), marca: str = Form(""),
    costo: str = Form("0"), precio_venta: str = Form("0"), stock_minimo: int = Form(0),
    proveedor: str = Form(""), caja: str = Form(""), estado: str = Form("activo"),
    precios_incluyen_impuesto: bool = Form(False),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    producto = db.get(Producto, producto_id)
    if producto:
        costo_final = to_decimal(costo)
        precio_final = to_decimal(precio_venta)
        if precios_incluyen_impuesto:
            tasa = _isv_tasa(db)
            costo_final = _quitar_impuesto(costo_final, tasa)
            precio_final = _quitar_impuesto(precio_final, tasa)
        producto.nombre = nombre.strip()
        producto.categoria = categoria
        producto.marca = marca
        producto.costo = costo_final
        producto.precio_venta = precio_final
        producto.stock_minimo = max(0, stock_minimo)
        producto.proveedor = proveedor
        producto.caja = caja.strip()
        producto.estado = estado
        db.commit()
        flash(request, "Producto actualizado.", "success")
    return RedirectResponse("/inventario", status_code=303)


@router.get("/inventario/{producto_id}/movimiento")
def inventario_movimiento_form(producto_id: int, request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    producto = db.get(Producto, producto_id)
    if not producto:
        flash(request, "Producto no encontrado.", "error")
        return RedirectResponse("/inventario", status_code=303)
    movimientos = db.query(MovimientoInventario).filter(MovimientoInventario.producto_id == producto_id).order_by(MovimientoInventario.fecha.desc()).all()
    return templates.TemplateResponse("inventario/movimiento.html", {
        "request": request, "producto": producto, "movimientos": movimientos, "usuario": usuario,
    })


@router.post("/inventario/{producto_id}/movimiento")
def inventario_registrar_movimiento(
    producto_id: int, request: Request,
    tipo: str = Form(...), cantidad: int = Form(...), motivo: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    producto = db.get(Producto, producto_id)
    if not producto:
        return RedirectResponse("/inventario", status_code=303)

    if cantidad <= 0:
        flash(request, "La cantidad debe ser mayor a cero.", "error")
        return RedirectResponse(f"/inventario/{producto_id}/movimiento", status_code=303)

    if tipo == "entrada":
        nueva_existencia = producto.existencia + cantidad
    elif tipo == "salida":
        if cantidad > producto.existencia:
            flash(request, "No hay suficiente existencia para esa salida.", "error")
            return RedirectResponse(f"/inventario/{producto_id}/movimiento", status_code=303)
        nueva_existencia = producto.existencia - cantidad
    elif tipo == "ajuste":
        nueva_existencia = cantidad  # el ajuste define la existencia final directamente
        if nueva_existencia < 0:
            flash(request, "La existencia no puede quedar negativa.", "error")
            return RedirectResponse(f"/inventario/{producto_id}/movimiento", status_code=303)
    else:
        flash(request, "Tipo de movimiento inválido.", "error")
        return RedirectResponse(f"/inventario/{producto_id}/movimiento", status_code=303)

    movimiento = MovimientoInventario(
        producto_id=producto.id, tipo=tipo, cantidad=cantidad, existencia_resultante=nueva_existencia,
        usuario_nombre=usuario["nombre_completo"], motivo=motivo,
    )
    producto.existencia = nueva_existencia
    db.add(movimiento)
    db.commit()
    flash(request, "Movimiento de inventario registrado.", "success")
    return RedirectResponse(f"/inventario/{producto_id}/movimiento", status_code=303)


@router.get("/inventario/plantilla")
def inventario_descargar_plantilla(usuario=Depends(login_required)):
    """Genera y descarga la plantilla de Excel para la carga masiva de
    inventario, con encabezados, un par de filas de ejemplo y una hoja de
    instrucciones."""
    wb = Workbook()

    hoja = wb.active
    hoja.title = "Inventario"
    encabezado_fill = PatternFill(start_color="121D33", end_color="121D33", fill_type="solid")
    encabezado_font = Font(bold=True, color="FFFFFF")
    for col, titulo in enumerate(COLUMNAS_PLANTILLA, start=1):
        celda = hoja.cell(row=1, column=col, value=titulo)
        celda.fill = encabezado_fill
        celda.font = encabezado_font
        celda.alignment = Alignment(vertical="center")

    ejemplo_font = Font(italic=True, color="888888")
    filas_ejemplo = [
        ["DEMO-001", "Ejemplo: Pantalla Samsung A32", "Repuestos", "Samsung", 250.00, 850.00, 5, 2, "Proveedor Ejemplo", "Caja 1"],
        ["DEMO-002", "Ejemplo: Batería iPhone 11", "Repuestos", "Apple", 180.00, 450.00, 3, 1, "Proveedor Ejemplo", "Caja 2"],
    ]
    for fila_idx, fila in enumerate(filas_ejemplo, start=2):
        for col_idx, valor in enumerate(fila, start=1):
            celda = hoja.cell(row=fila_idx, column=col_idx, value=valor)
            celda.font = ejemplo_font

    anchos = [14, 34, 16, 16, 12, 16, 12, 13, 20, 12]
    for col_idx, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[hoja.cell(row=1, column=col_idx).column_letter].width = ancho
    hoja.freeze_panes = "A2"

    instrucciones = wb.create_sheet("Instrucciones")
    instrucciones.column_dimensions["A"].width = 26
    instrucciones.column_dimensions["B"].width = 90
    filas_instrucciones = [
        ("Cómo usar esta plantilla", ""),
        ("1.", "Borra las dos filas de ejemplo (DEMO-001 y DEMO-002) de la hoja \"Inventario\" antes de importar, o simplemente sobrescríbelas."),
        ("2.", "Llena una fila por cada producto. No cambies el orden ni los nombres de las columnas."),
        ("3.", "Código (obligatorio): identifica el producto. Si el código YA existe en el sistema, se actualiza ese producto; si no existe, se crea uno nuevo."),
        ("4.", "Nombre (obligatorio)."),
        ("5.", "Categoría, Marca y Proveedor son opcionales."),
        ("6.", "Costo y Precio de venta: números, por ejemplo 250.00. Si los dejas en blanco en un producto que ya existe, no se modifica el que ya tenía guardado."),
        ("7.", "Existencia: si el producto es NUEVO, se usa como la existencia inicial. Si el producto YA EXISTE, la cantidad que pongas se SUMA a la existencia actual (como una entrada de inventario), no la reemplaza. Déjala en blanco si no quieres modificar la existencia."),
        ("8.", "Stock mínimo: cantidad a partir de la cual el sistema avisa \"Bajo\". Opcional."),
        ("9.", "Caja: el número o nombre de la caja/casillero donde tienes guardado el repuesto (por ejemplo \"Caja 3\" o \"Estante A-2\"). Opcional, solo para ubicarlo más rápido."),
        ("10.", "Costo y Precio de venta con impuesto incluido: si prefieres escribir el número redondo que ya incluye el impuesto y que el sistema le reste el ISV automáticamente para guardarlo, marca la casilla \"Estos precios ya incluyen impuesto\" al subir el archivo, en el Paso 2."),
        ("11.", "Guarda el archivo en formato Excel (.xlsx) y súbelo en Inventario → Carga masiva (Excel)."),
    ]
    for fila_idx, (a, b) in enumerate(filas_instrucciones, start=1):
        celda_a = instrucciones.cell(row=fila_idx, column=1, value=a)
        instrucciones.cell(row=fila_idx, column=2, value=b)
        if fila_idx == 1:
            celda_a.font = Font(bold=True, size=13)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="plantilla_inventario.xlsx"'},
    )


@router.get("/inventario/importar")
def inventario_importar_form(request: Request, usuario=Depends(login_required)):
    return templates.TemplateResponse("inventario/importar.html", {"request": request, "usuario": usuario})


def _leer_texto(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def _leer_numero(valor):
    """Devuelve (encontrado, valor_decimal). encontrado=False si la celda
    estaba vacía, para poder distinguir 'no lo toques' de 'ponlo en 0'."""
    if valor is None or str(valor).strip() == "":
        return False, to_decimal(0)
    return True, to_decimal(valor)


def _leer_entero(valor):
    if valor is None or str(valor).strip() == "":
        return False, 0
    try:
        return True, int(float(valor))
    except (TypeError, ValueError):
        return True, None  # marca inválido


@router.post("/inventario/importar")
async def inventario_importar_procesar(
    request: Request, archivo: UploadFile = File(...),
    precios_incluyen_impuesto: bool = Form(False),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    nombre_archivo = archivo.filename or ""
    if not nombre_archivo.lower().endswith((".xlsx", ".xlsm")):
        flash(request, "El archivo debe ser un Excel (.xlsx). Descarga la plantilla e inténtalo de nuevo.", "error")
        return RedirectResponse("/inventario/importar", status_code=303)

    tasa_isv = _isv_tasa(db) if precios_incluyen_impuesto else None
    contenido = await archivo.read()
    try:
        wb = load_workbook(io.BytesIO(contenido), data_only=True)
    except Exception:
        flash(request, "No se pudo leer el archivo. Asegúrate de que sea un Excel válido (.xlsx) y no esté dañado.", "error")
        return RedirectResponse("/inventario/importar", status_code=303)

    hoja = wb["Inventario"] if "Inventario" in wb.sheetnames else wb.worksheets[0]

    resultados = []
    creados = actualizados = con_error = 0
    MAX_FILAS = 2000

    for i, fila in enumerate(hoja.iter_rows(min_row=2, max_row=1 + MAX_FILAS, values_only=True), start=2):
        if fila is None or all(c is None or str(c).strip() == "" for c in fila):
            continue  # fila completamente vacía, se ignora sin reportarla

        codigo = _leer_texto(fila[0] if len(fila) > 0 else None)
        nombre = _leer_texto(fila[1] if len(fila) > 1 else None)
        categoria = _leer_texto(fila[2] if len(fila) > 2 else None)
        marca = _leer_texto(fila[3] if len(fila) > 3 else None)
        hay_costo, costo = _leer_numero(fila[4] if len(fila) > 4 else None)
        hay_precio, precio_venta = _leer_numero(fila[5] if len(fila) > 5 else None)
        hay_existencia, existencia = _leer_entero(fila[6] if len(fila) > 6 else None)
        hay_stock_min, stock_minimo = _leer_entero(fila[7] if len(fila) > 7 else None)
        proveedor = _leer_texto(fila[8] if len(fila) > 8 else None)
        caja = _leer_texto(fila[9] if len(fila) > 9 else None)

        if hay_costo and tasa_isv is not None:
            costo = _quitar_impuesto(costo, tasa_isv)
        if hay_precio and tasa_isv is not None:
            precio_venta = _quitar_impuesto(precio_venta, tasa_isv)

        if codigo.upper() in ("DEMO-001", "DEMO-002"):
            continue  # fila de ejemplo que el usuario olvidó borrar

        if not codigo:
            con_error += 1
            resultados.append({"fila": i, "codigo": "-", "nombre": nombre or "-", "resultado": "error", "detalle": "Falta el código."})
            continue
        if not nombre:
            con_error += 1
            resultados.append({"fila": i, "codigo": codigo, "nombre": "-", "resultado": "error", "detalle": "Falta el nombre."})
            continue
        if hay_existencia and existencia is None:
            con_error += 1
            resultados.append({"fila": i, "codigo": codigo, "nombre": nombre, "resultado": "error", "detalle": "La existencia debe ser un número."})
            continue
        if hay_existencia and existencia < 0:
            con_error += 1
            resultados.append({"fila": i, "codigo": codigo, "nombre": nombre, "resultado": "error", "detalle": "La existencia no puede ser negativa."})
            continue
        if hay_stock_min and stock_minimo is None:
            con_error += 1
            resultados.append({"fila": i, "codigo": codigo, "nombre": nombre, "resultado": "error", "detalle": "El stock mínimo debe ser un número."})
            continue
        if hay_stock_min and stock_minimo < 0:
            con_error += 1
            resultados.append({"fila": i, "codigo": codigo, "nombre": nombre, "resultado": "error", "detalle": "El stock mínimo no puede ser negativo."})
            continue

        producto = db.query(Producto).filter(Producto.codigo == codigo).first()
        if producto:
            producto.nombre = nombre
            if categoria:
                producto.categoria = categoria
            if marca:
                producto.marca = marca
            if proveedor:
                producto.proveedor = proveedor
            if caja:
                producto.caja = caja
            if hay_costo:
                producto.costo = costo
            if hay_precio:
                producto.precio_venta = precio_venta
            if hay_stock_min:
                producto.stock_minimo = max(0, stock_minimo)
            detalle = "Datos actualizados."
            if hay_existencia and existencia > 0:
                nueva_existencia = producto.existencia + existencia
                db.add(MovimientoInventario(
                    producto_id=producto.id, tipo="entrada", cantidad=existencia,
                    existencia_resultante=nueva_existencia, usuario_nombre=usuario["nombre_completo"],
                    motivo="Carga masiva por Excel",
                ))
                producto.existencia = nueva_existencia
                detalle = f"Datos actualizados y se sumaron {existencia} unidades (existencia nueva: {nueva_existencia})."
            actualizados += 1
            resultados.append({"fila": i, "codigo": codigo, "nombre": nombre, "resultado": "actualizado", "detalle": detalle})
        else:
            producto = Producto(
                codigo=codigo, nombre=nombre, categoria=categoria, marca=marca,
                costo=costo if hay_costo else to_decimal(0), precio_venta=precio_venta if hay_precio else to_decimal(0),
                existencia=max(0, existencia) if hay_existencia else 0,
                stock_minimo=max(0, stock_minimo) if hay_stock_min else 0,
                proveedor=proveedor, caja=caja, estado="activo",
            )
            db.add(producto)
            db.flush()  # para que códigos repetidos en el mismo archivo se vean como "ya existe" en la fila siguiente
            creados += 1
            resultados.append({"fila": i, "codigo": codigo, "nombre": nombre, "resultado": "creado", "detalle": "Producto nuevo creado."})

    db.commit()

    return templates.TemplateResponse("inventario/importar_resultado.html", {
        "request": request, "usuario": usuario, "resultados": resultados,
        "creados": creados, "actualizados": actualizados, "con_error": con_error,
        "total_filas": len(resultados),
    })
