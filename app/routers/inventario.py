"""Módulo de inventario: productos, entradas, salidas, ajustes y alertas de stock."""
import io
import json
from urllib.parse import quote
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation

from app.templates_env import templates
from app.database import get_db
from app.models import Producto, MovimientoInventario, ConfiguracionFacturacion, Categoria
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


def _categorias_disponibles(db: Session):
    """Nombres de las categorías activas del catálogo controlado (para el
    filtro de Inventario y los <select> de los formularios)."""
    filas = (
        db.query(Categoria.nombre)
        .filter(Categoria.activo == True)  # noqa: E712
        .order_by(Categoria.nombre)
        .all()
    )
    return [f[0] for f in filas]


def _ultimo_producto(db: Session):
    """El producto ingresado más recientemente (para mostrar cuál fue el
    último código usado)."""
    return db.query(Producto).order_by(Producto.creado_en.desc(), Producto.id.desc()).first()


# ---------------------------------------------------------------------------
# Categorías: catálogo controlado. Hay que crearlas aquí antes de poder
# asignarlas a un producto (evita duplicados como "PANTALLA"/"PANTALLAS").
# ---------------------------------------------------------------------------
@router.get("/inventario/categorias")
def categorias_list(request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    categorias = db.query(Categoria).order_by(Categoria.nombre).all()
    # Cuenta cuántos productos usan cada categoría (para no dejar eliminar
    # una que sigue en uso).
    filas_conteo = (
        db.query(Producto.categoria, Producto.id)
        .filter(Producto.categoria.isnot(None), Producto.categoria != "")
        .all()
    )
    en_uso = {}
    for cat, _ in filas_conteo:
        en_uso[cat] = en_uso.get(cat, 0) + 1
    return templates.TemplateResponse("inventario/categorias.html", {
        "request": request, "usuario": usuario, "categorias": categorias, "en_uso": en_uso,
    })


@router.post("/inventario/categorias")
def categorias_crear(
    request: Request, nombre: str = Form(...),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    nombre = nombre.strip()
    if not nombre:
        flash(request, "Escribe un nombre para la categoría.", "error")
        return RedirectResponse("/inventario/categorias", status_code=303)
    existe = db.query(Categoria).filter(Categoria.nombre.ilike(nombre)).first()
    if existe:
        flash(request, f"La categoría '{existe.nombre}' ya existe.", "error")
        return RedirectResponse("/inventario/categorias", status_code=303)
    db.add(Categoria(nombre=nombre, activo=True))
    db.commit()
    flash(request, f"Categoría '{nombre}' creada. Ya puedes elegirla al crear o editar productos.", "success")
    return RedirectResponse("/inventario/categorias", status_code=303)


@router.post("/inventario/categorias/{categoria_id}/activar")
def categorias_toggle(
    categoria_id: int, request: Request,
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    cat = db.get(Categoria, categoria_id)
    if cat:
        cat.activo = not cat.activo
        db.commit()
        flash(request, f"Categoría '{cat.nombre}' {'activada' if cat.activo else 'desactivada'}.", "success")
    return RedirectResponse("/inventario/categorias", status_code=303)


@router.post("/inventario/categorias/{categoria_id}/eliminar")
def categorias_eliminar(
    categoria_id: int, request: Request,
    db: Session = Depends(get_db), usuario=Depends(roles_required("admin")),
):
    cat = db.get(Categoria, categoria_id)
    if not cat:
        return RedirectResponse("/inventario/categorias", status_code=303)
    en_uso = db.query(Producto).filter(Producto.categoria.ilike(cat.nombre)).count()
    if en_uso > 0:
        flash(request, f"No se puede eliminar '{cat.nombre}': la usan {en_uso} producto(s). Desactívala en vez de eliminarla.", "error")
        return RedirectResponse("/inventario/categorias", status_code=303)
    db.delete(cat)
    db.commit()
    flash(request, f"Categoría '{cat.nombre}' eliminada.", "success")
    return RedirectResponse("/inventario/categorias", status_code=303)


@router.get("/inventario")
def inventario_list(request: Request, q: str = "", categoria: str = "", db: Session = Depends(get_db), usuario=Depends(login_required)):
    query = db.query(Producto)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Producto.codigo.ilike(like), Producto.nombre.ilike(like),
                                  Producto.categoria.ilike(like), Producto.marca.ilike(like)))
    if categoria:
        query = query.filter(Producto.categoria == categoria)
    productos = query.order_by(Producto.nombre).all()
    stock_bajo_ids = {p.id for p in productos if p.existencia <= p.stock_minimo}
    total_inversion = sum((to_decimal(p.costo) * p.existencia for p in productos), to_decimal(0))
    ultimo_producto = _ultimo_producto(db)
    return templates.TemplateResponse("inventario/list.html", {
        "request": request, "productos": productos, "q": q, "categoria": categoria,
        "categorias_disponibles": _categorias_disponibles(db),
        "usuario": usuario, "stock_bajo_ids": stock_bajo_ids, "total_inversion": total_inversion,
        "ultimo_producto": ultimo_producto,
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


@router.get("/inventario/exportar/excel")
def inventario_exportar_excel(q: str = "", categoria: str = "", db: Session = Depends(get_db), usuario=Depends(login_required)):
    """Descarga en Excel (.xlsx) los productos que coinciden con el
    buscador y la categoría seleccionados en la lista de Inventario (si no
    hay filtros aplicados, descarga todo el inventario). Se ordenan del
    más reciente al más antiguo (según la fecha en que se ingresó cada
    producto), para que el último código usado quede siempre de primero."""
    query = db.query(Producto)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Producto.codigo.ilike(like), Producto.nombre.ilike(like),
                                  Producto.categoria.ilike(like), Producto.marca.ilike(like)))
    if categoria:
        query = query.filter(Producto.categoria == categoria)
    productos = query.order_by(Producto.creado_en.desc(), Producto.id.desc()).all()

    wb = Workbook()
    hoja = wb.active
    hoja.title = "Inventario"

    encabezados = ["Código", "Nombre", "Categoría", "Marca", "Caja", "Costo", "Precio de venta", "Existencia", "Stock mínimo", "Estado"]
    encabezado_fill = PatternFill(start_color="121D33", end_color="121D33", fill_type="solid")
    encabezado_font = Font(bold=True, color="FFFFFF")
    for col, titulo in enumerate(encabezados, start=1):
        celda = hoja.cell(row=1, column=col, value=titulo)
        celda.fill = encabezado_fill
        celda.font = encabezado_font
        celda.alignment = Alignment(vertical="center")

    for fila_idx, p in enumerate(productos, start=2):
        valores = [
            p.codigo, p.nombre, p.categoria or "", p.marca or "", p.caja or "",
            float(p.costo), float(p.precio_venta), p.existencia, p.stock_minimo,
            "Activo" if p.estado == "activo" else "Inactivo",
        ]
        for col_idx, valor in enumerate(valores, start=1):
            hoja.cell(row=fila_idx, column=col_idx, value=valor)

    anchos = [14, 34, 16, 16, 12, 12, 16, 12, 13, 10]
    for col_idx, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[hoja.cell(row=1, column=col_idx).column_letter].width = ancho
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = f"A1:{hoja.cell(row=1, column=len(encabezados)).column_letter}{max(len(productos) + 1, 1)}"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    nombre_archivo = "inventario_filtrado.xlsx" if (q or categoria) else "inventario.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


@router.get("/inventario/nuevo")
def inventario_nuevo_form(request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    return templates.TemplateResponse("inventario/form.html", {
        "request": request, "producto": None, "usuario": usuario, "ultimo_producto": _ultimo_producto(db),
        "categorias": _categorias_disponibles(db),
    })


def _categoria_valida(db: Session, categoria: str) -> bool:
    """True si la categoría viene vacía o coincide con una ya creada en el
    catálogo (sin importar mayúsculas/minúsculas)."""
    if not categoria:
        return True
    return db.query(Categoria).filter(Categoria.nombre.ilike(categoria)).first() is not None


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
    if not _categoria_valida(db, categoria):
        flash(request, "Esa categoría no existe. Créala primero en Inventario → Categorías.", "error")
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
    return templates.TemplateResponse("inventario/form.html", {
        "request": request, "producto": producto, "usuario": usuario,
        "categorias": _categorias_disponibles(db),
    })


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
        if categoria != producto.categoria and not _categoria_valida(db, categoria):
            flash(request, "Esa categoría no existe. Créala primero en Inventario → Categorías.", "error")
            return RedirectResponse(f"/inventario/{producto_id}/editar", status_code=303)
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


# ---------------------------------------------------------------------------
# Ajuste rápido de existencias: buscar un producto y ajustarlo ahí mismo,
# sin tener que entrar primero a Inventario y abrir ese producto.
# ---------------------------------------------------------------------------
@router.get("/inventario/ajustes")
def inventario_ajustes_form(request: Request, q: str = "", db: Session = Depends(get_db), usuario=Depends(login_required)):
    productos = []
    if q:
        like = f"%{q}%"
        productos = db.query(Producto).filter(
            or_(Producto.codigo.ilike(like), Producto.nombre.ilike(like))
        ).order_by(Producto.nombre).all()
    return templates.TemplateResponse("inventario/ajustes.html", {
        "request": request, "q": q, "productos": productos, "usuario": usuario,
    })


@router.post("/inventario/ajustes/{producto_id}")
def inventario_ajustes_procesar(
    producto_id: int, request: Request,
    tipo: str = Form(...), cantidad: int = Form(...), motivo: str = Form(""), q: str = Form(""),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    destino = f"/inventario/ajustes?q={quote(q)}"
    producto = db.get(Producto, producto_id)
    if not producto:
        flash(request, "Producto no encontrado.", "error")
        return RedirectResponse(destino, status_code=303)

    if cantidad <= 0:
        flash(request, "La cantidad debe ser mayor a cero.", "error")
        return RedirectResponse(destino, status_code=303)

    if tipo == "entrada":
        nueva_existencia = producto.existencia + cantidad
    elif tipo == "salida":
        if cantidad > producto.existencia:
            flash(request, f"No hay suficiente existencia de {producto.nombre} para esa salida.", "error")
            return RedirectResponse(destino, status_code=303)
        nueva_existencia = producto.existencia - cantidad
    elif tipo == "ajuste":
        nueva_existencia = cantidad  # el ajuste define la existencia final directamente
        if nueva_existencia < 0:
            flash(request, "La existencia no puede quedar negativa.", "error")
            return RedirectResponse(destino, status_code=303)
    else:
        flash(request, "Tipo de movimiento inválido.", "error")
        return RedirectResponse(destino, status_code=303)

    movimiento = MovimientoInventario(
        producto_id=producto.id, tipo=tipo, cantidad=cantidad, existencia_resultante=nueva_existencia,
        usuario_nombre=usuario["nombre_completo"], motivo=motivo,
    )
    producto.existencia = nueva_existencia
    db.add(movimiento)
    db.commit()
    flash(request, f"Existencia de {producto.nombre} actualizada a {nueva_existencia}.", "success")
    return RedirectResponse(destino, status_code=303)


@router.get("/inventario/plantilla")
def inventario_descargar_plantilla(db: Session = Depends(get_db), usuario=Depends(login_required)):
    """Genera y descarga la plantilla de Excel para la carga masiva de
    inventario, con encabezados, un par de filas de ejemplo y una hoja de
    instrucciones."""
    categorias = _categorias_disponibles(db)
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

    # Columna "Categoría" (C) como lista desplegable: solo se puede elegir
    # una categoría ya creada en Inventario → Categorías.
    if categorias:
        hoja_cat = wb.create_sheet("ListaCategorias")
        for i, nombre in enumerate(categorias, start=1):
            hoja_cat.cell(row=i, column=1, value=nombre)
        hoja_cat.sheet_state = "hidden"
        dv = DataValidation(
            type="list", formula1=f"=ListaCategorias!$A$1:$A${len(categorias)}",
            allow_blank=True,
        )
        dv.error = "Esa categoría no existe. Créala primero en Inventario → Categorías antes de usarla aquí."
        dv.errorTitle = "Categoría inválida"
        dv.prompt = "Elige una categoría de la lista (o déjalo en blanco)."
        dv.promptTitle = "Categoría"
        hoja.add_data_validation(dv)
        dv.add("C2:C2001")

    instrucciones = wb.create_sheet("Instrucciones")
    instrucciones.column_dimensions["A"].width = 26
    instrucciones.column_dimensions["B"].width = 90
    filas_instrucciones = [
        ("Cómo usar esta plantilla", ""),
        ("1.", "Borra las dos filas de ejemplo (DEMO-001 y DEMO-002) de la hoja \"Inventario\" antes de importar, o simplemente sobrescríbelas."),
        ("2.", "Llena una fila por cada producto. No cambies el orden ni los nombres de las columnas."),
        ("3.", "Código (obligatorio): identifica el producto. Si el código YA existe en el sistema, se actualiza ese producto; si no existe, se crea uno nuevo."),
        ("4.", "Nombre (obligatorio)."),
        ("5.", "Categoría: elige una de la lista desplegable de la celda (solo se pueden usar categorías ya creadas en Inventario → Categorías). Marca y Proveedor son texto libre y opcionales."),
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


def _parsear_y_validar_fila(fila, i, categorias_validas, tasa_isv):
    """Lee y valida UNA fila de la plantilla de carga masiva, sin tocar la
    base de datos todavía (esto es lo que permite mostrar la vista previa
    antes de importar). Devuelve None si la fila debe ignorarse (vacía o la
    fila de ejemplo DEMO), o un dict con 'estado' = 'error' (algo está mal
    en esa fila) u 'ok' (fila válida; falta decidir si va a crear o
    actualizar un producto, lo cual se hace después comparando contra la
    base de datos y contra el resto del archivo)."""
    if fila is None or all(c is None or str(c).strip() == "" for c in fila):
        return None

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
        return None  # fila de ejemplo que el usuario olvidó borrar

    def _error(detalle):
        return {"fila": i, "codigo": codigo or "-", "nombre": nombre or "-", "estado": "error", "detalle": detalle}

    if not codigo:
        return _error("Falta el código.")
    if not nombre:
        return _error("Falta el nombre.")
    if hay_existencia and existencia is None:
        return _error("La existencia debe ser un número.")
    if hay_existencia and existencia < 0:
        return _error("La existencia no puede ser negativa.")
    if hay_stock_min and stock_minimo is None:
        return _error("El stock mínimo debe ser un número.")
    if hay_stock_min and stock_minimo < 0:
        return _error("El stock mínimo no puede ser negativo.")
    if categoria and categoria.lower() not in categorias_validas:
        return _error(f"La categoría '{categoria}' no existe. Créala primero en Inventario → Categorías.")

    return {
        "fila": i, "codigo": codigo, "nombre": nombre, "estado": "ok",
        "categoria": categoria, "marca": marca,
        "costo": str(costo), "hay_costo": hay_costo,
        "precio_venta": str(precio_venta), "hay_precio": hay_precio,
        "existencia": existencia, "hay_existencia": hay_existencia,
        "stock_minimo": stock_minimo, "hay_stock_min": hay_stock_min,
        "proveedor": proveedor, "caja": caja,
    }


def _construir_vista_previa(hoja, db, tasa_isv):
    """Recorre el Excel y arma, SIN escribir nada en la base de datos, la
    lista de lo que pasaría con cada fila: 'creara' (producto nuevo),
    'actualizara' (ya existe ese código) o 'error' (no se puede importar)."""
    categorias_validas = {fila[0].lower() for fila in db.query(Categoria.nombre).all()}
    MAX_FILAS = 2000
    filas_info = []
    for i, fila in enumerate(hoja.iter_rows(min_row=2, max_row=1 + MAX_FILAS, values_only=True), start=2):
        info = _parsear_y_validar_fila(fila, i, categorias_validas, tasa_isv)
        if info is not None:
            filas_info.append(info)

    # Códigos repetidos DENTRO del mismo archivo (sin importar mayúsculas):
    # ninguna de esas filas se importa hasta que el usuario corrija su
    # Excel, para que nunca se termine pisando un producto con los datos
    # de otro por accidente.
    filas_por_codigo = {}
    for info in filas_info:
        if info["estado"] == "ok":
            filas_por_codigo.setdefault(info["codigo"].upper(), []).append(info["fila"])

    for info in filas_info:
        if info["estado"] != "ok":
            continue
        otras = [f for f in filas_por_codigo[info["codigo"].upper()] if f != info["fila"]]
        if otras:
            info["estado"] = "error"
            info["detalle"] = (
                "Este código se repite en tu archivo (también en la fila "
                + ", ".join(str(f) for f in otras) + "). Corrígelo antes de importar: "
                "cada código debe aparecer una sola vez."
            )

    # Para las filas que sí quedan válidas: ¿el código ya existe en el
    # sistema? Si es así se avisa con qué producto exactamente, para que
    # se note enseguida si fue un código mal escrito por error.
    for info in filas_info:
        if info["estado"] != "ok":
            continue
        producto = db.query(Producto).filter(Producto.codigo == info["codigo"]).first()
        if producto:
            info["estado"] = "actualizara"
            partes = [f'Ya existe como "{producto.nombre}"']
            if producto.categoria:
                partes.append(f"({producto.categoria})")
            info["detalle"] = " ".join(partes) + " — se actualizará, NO se creará un producto nuevo."
        else:
            info["estado"] = "creara"
            info["detalle"] = "Producto nuevo."

    return filas_info


@router.post("/inventario/importar")
async def inventario_importar_procesar(
    request: Request, archivo: UploadFile = File(...),
    precios_incluyen_impuesto: bool = Form(False),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    """Primer paso de la carga masiva: lee el Excel y muestra una VISTA
    PREVIA de lo que se va a crear/actualizar (sin tocar la base de datos
    todavía), para que el usuario la revise y confirme antes de importar."""
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
    filas_info = _construir_vista_previa(hoja, db, tasa_isv)

    creara = sum(1 for f in filas_info if f["estado"] == "creara")
    actualizara = sum(1 for f in filas_info if f["estado"] == "actualizara")
    con_error = sum(1 for f in filas_info if f["estado"] == "error")
    filas_importables = [f for f in filas_info if f["estado"] in ("creara", "actualizara")]

    return templates.TemplateResponse("inventario/importar_preview.html", {
        "request": request, "usuario": usuario, "filas_info": filas_info,
        "creara": creara, "actualizara": actualizara, "con_error": con_error,
        "total_filas": len(filas_info), "nombre_archivo": nombre_archivo,
        "filas_json": json.dumps(filas_importables),
    })


@router.post("/inventario/importar/confirmar")
async def inventario_importar_confirmar(
    request: Request, filas_json: str = Form(...),
    db: Session = Depends(get_db), usuario=Depends(login_required),
):
    """Segundo paso: el usuario ya vio la vista previa y confirmó, así que
    ahora sí se escribe en la base de datos. Usa exactamente las filas que
    se mostraron en la vista previa (nada se vuelve a leer del Excel)."""
    try:
        filas = json.loads(filas_json)
        assert isinstance(filas, list)
    except (ValueError, TypeError, AssertionError):
        flash(request, "La vista previa expiró o no se pudo leer. Vuelve a subir el archivo.", "error")
        return RedirectResponse("/inventario/importar", status_code=303)

    if not filas:
        flash(request, "No había ninguna fila para importar.", "error")
        return RedirectResponse("/inventario/importar", status_code=303)

    categorias_validas = {fila[0].lower() for fila in db.query(Categoria.nombre).all()}
    resultados = []
    creados = actualizados = con_error = 0

    for info in filas:
        i = info.get("fila")
        codigo = (info.get("codigo") or "").strip()
        nombre = (info.get("nombre") or "").strip()
        categoria = (info.get("categoria") or "").strip()
        marca = info.get("marca") or ""
        proveedor = info.get("proveedor") or ""
        caja = info.get("caja") or ""
        hay_costo = bool(info.get("hay_costo"))
        hay_precio = bool(info.get("hay_precio"))
        hay_existencia = bool(info.get("hay_existencia"))
        hay_stock_min = bool(info.get("hay_stock_min"))
        costo = to_decimal(info.get("costo")) if hay_costo else to_decimal(0)
        precio_venta = to_decimal(info.get("precio_venta")) if hay_precio else to_decimal(0)
        existencia = info.get("existencia") if hay_existencia else 0
        stock_minimo = info.get("stock_minimo") if hay_stock_min else 0

        if not codigo or not nombre:
            con_error += 1
            resultados.append({"fila": i, "codigo": codigo or "-", "nombre": nombre or "-", "resultado": "error",
                                "detalle": "Fila inválida: vuelve a subir el archivo y genera la vista previa de nuevo."})
            continue
        # La categoría se vuelve a validar por si acaso: pudo eliminarse o
        # desactivarse entre que se generó la vista previa y se confirmó.
        if categoria and categoria.lower() not in categorias_validas:
            con_error += 1
            resultados.append({"fila": i, "codigo": codigo, "nombre": nombre, "resultado": "error",
                                "detalle": f"La categoría '{categoria}' ya no existe. Créala en Inventario → Categorías y vuelve a intentarlo."})
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
            if hay_existencia and existencia and existencia > 0:
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
                costo=costo, precio_venta=precio_venta,
                existencia=max(0, existencia or 0), stock_minimo=max(0, stock_minimo or 0),
                proveedor=proveedor, caja=caja, estado="activo",
            )
            db.add(producto)
            db.flush()
            creados += 1
            resultados.append({"fila": i, "codigo": codigo, "nombre": nombre, "resultado": "creado", "detalle": "Producto nuevo creado."})

    db.commit()

    return templates.TemplateResponse("inventario/importar_resultado.html", {
        "request": request, "usuario": usuario, "resultados": resultados,
        "creados": creados, "actualizados": actualizados, "con_error": con_error,
        "total_filas": len(resultados),
    })
