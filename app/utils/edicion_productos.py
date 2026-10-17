"""Edición de los datos de un producto (uno o varios a la vez) con su
historial: cada campo que cambia queda en HistorialProducto.
Las existencias NO se editan aquí (entran con Compras y se corrigen con
Ajustes de inventario)."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models import Producto, HistorialProducto, Categoria
from app.utils.calculations import to_decimal

CENT = Decimal("0.01")
CAMPOS = {
    "nombre": "Nombre", "categoria": "Categoría", "marca": "Marca", "costo": "Costo",
    "precio_venta": "Precio de venta", "stock_minimo": "Stock mínimo", "caja": "Caja",
    "proveedor": "Proveedor", "estado": "Estado",
}


def quitar_isv(valor: Decimal, tasa) -> Decimal:
    return (to_decimal(valor) / (1 + to_decimal(tasa) / 100)).quantize(CENT)


def _texto(campo, valor) -> str:
    if valor is None:
        return ""
    if campo in ("costo", "precio_venta"):
        return f"{to_decimal(valor):,.2f}"
    return str(valor)


def leer_monto(texto: str, nombre: str, con_isv: bool, tasa) -> Decimal:
    t = (texto or "").strip().replace(",", "")
    if t == "":
        raise ValueError(f"{nombre}: falta el número.")
    try:
        v = to_decimal(t)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{nombre}: escribe un número válido.")
    if v < 0:
        raise ValueError(f"{nombre}: no puede ser negativo.")
    return quitar_isv(v, tasa) if con_isv else v.quantize(CENT)


def categorias_validas(db: Session) -> dict:
    """nombre en minúsculas -> nombre como está guardado (activas)."""
    return {c.nombre.lower(): c.nombre for c in db.query(Categoria).filter(Categoria.activo == True).all()}  # noqa: E712


def validar(datos: dict, producto: Producto, cats: dict, tasa, costo_con_isv: bool, precio_con_isv: bool):
    """datos crudos del formulario -> (valores limpios, errores[])."""
    errores, v = [], {}
    v["nombre"] = (datos.get("nombre") or "").strip()
    if not v["nombre"]:
        errores.append("el nombre no puede quedar vacío")
    cat = (datos.get("categoria") or "").strip()
    if cat and cat.lower() not in cats and cat != (producto.categoria or ""):
        errores.append(f"la categoría «{cat}» no existe")
    v["categoria"] = cats.get(cat.lower(), cat) if cat else ""
    for campo in ("marca", "caja", "proveedor"):
        if campo in datos:
            v[campo] = (datos.get(campo) or "").strip()
    try:
        v["costo"] = leer_monto(datos.get("costo"), "Costo", costo_con_isv, tasa)
    except ValueError as e:
        errores.append(str(e))
    try:
        v["precio_venta"] = leer_monto(datos.get("precio_venta"), "Precio de venta", precio_con_isv, tasa)
    except ValueError as e:
        errores.append(str(e))
    if "costo" in v and "precio_venta" in v and v["precio_venta"] > 0 and v["precio_venta"] < v["costo"]:
        errores.append(f"el precio de venta ({v['precio_venta']:,.2f} sin ISV) queda por debajo del costo ({v['costo']:,.2f})")
    if "stock_minimo" in datos:
        try:
            v["stock_minimo"] = max(0, int((datos.get("stock_minimo") or "0").strip() or 0))
        except ValueError:
            errores.append("el stock mínimo debe ser un número entero")
    if "estado" in datos:
        v["estado"] = "inactivo" if datos.get("estado") == "inactivo" else "activo"
    return v, errores


def aplicar(db: Session, producto: Producto, valores: dict, usuario_nombre: str, origen: str) -> list[str]:
    """Aplica los valores que cambiaron y los deja en el historial.
    Devuelve los nombres de los campos cambiados."""
    cambiados = []
    ahora = datetime.utcnow()
    for campo, nuevo in valores.items():
        actual = getattr(producto, campo)
        if campo in ("costo", "precio_venta"):
            igual = to_decimal(actual or 0).quantize(CENT) == to_decimal(nuevo).quantize(CENT)
        else:
            igual = (actual if actual is not None else "") == (nuevo if nuevo is not None else "")
        if igual:
            continue
        db.add(HistorialProducto(producto_id=producto.id, fecha=ahora, usuario_nombre=usuario_nombre, campo=campo,
                                 antes=_texto(campo, actual)[:200], despues=_texto(campo, nuevo)[:200], origen=origen))
        setattr(producto, campo, nuevo)
        cambiados.append(CAMPOS.get(campo, campo))
    return cambiados
