"""Punto de venta (POS): carrito, cálculo de totales, cobro y descuento de inventario."""
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.templates_env import templates
from app.database import get_db
from app.models import Producto, Venta, DetalleVenta, MovimientoInventario, MovimientoFinanciero, Cliente
from app.schemas import VentaIn
from app.utils.numbering import generar_numero_venta
from app.utils.calculations import to_decimal
from app.deps import login_required

router = APIRouter()


@router.get("/pos")
def pos_index(request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    productos = db.query(Producto).filter(Producto.estado == "activo", Producto.existencia > 0).order_by(Producto.nombre).all()
    clientes = db.query(Cliente).order_by(Cliente.nombre).all()
    return templates.TemplateResponse("pos/index.html", {
        "request": request, "productos": productos, "clientes": clientes, "usuario": usuario,
    })


@router.post("/pos/vender")
def pos_vender(request: Request, venta_in: VentaIn, db: Session = Depends(get_db), usuario=Depends(login_required)):
    if not venta_in.items:
        return JSONResponse({"ok": False, "mensaje": "El carrito está vacío."}, status_code=400)

    subtotal = Decimal("0")
    detalles = []
    for item in venta_in.items:
        producto = db.get(Producto, item.producto_id)
        if not producto:
            return JSONResponse({"ok": False, "mensaje": f"Producto {item.producto_id} no encontrado."}, status_code=400)
        if item.cantidad > producto.existencia:
            return JSONResponse({"ok": False, "mensaje": f"No hay suficiente existencia de '{producto.nombre}'."}, status_code=400)
        precio = to_decimal(producto.precio_venta)
        sub = (precio * item.cantidad).quantize(Decimal("0.01"))
        subtotal += sub
        detalles.append((producto, item.cantidad, precio, sub))

    descuento = to_decimal(venta_in.descuento)
    if descuento < 0 or descuento > subtotal:
        return JSONResponse({"ok": False, "mensaje": "El descuento no es válido."}, status_code=400)

    total = (subtotal - descuento).quantize(Decimal("0.01"))
    monto_recibido = to_decimal(venta_in.monto_recibido)
    if monto_recibido < total:
        return JSONResponse({"ok": False, "mensaje": "El monto recibido es menor al total a pagar."}, status_code=400)
    cambio = (monto_recibido - total).quantize(Decimal("0.01"))

    venta = Venta(
        numero_venta=generar_numero_venta(db), cliente_id=venta_in.cliente_id,
        subtotal=subtotal, descuento=descuento, total=total,
        forma_pago=venta_in.forma_pago, monto_recibido=monto_recibido, cambio=cambio,
        usuario_nombre=usuario["nombre_completo"],
    )
    db.add(venta)
    db.flush()

    for producto, cantidad, precio, sub in detalles:
        db.add(DetalleVenta(venta_id=venta.id, producto_id=producto.id, cantidad=cantidad,
                             precio_unitario=precio, subtotal=sub))
        producto.existencia -= cantidad
        db.add(MovimientoInventario(
            producto_id=producto.id, tipo="salida", cantidad=cantidad,
            existencia_resultante=producto.existencia, usuario_nombre=usuario["nombre_completo"],
            motivo=f"Venta {venta.numero_venta}",
        ))

    db.add(MovimientoFinanciero(
        tipo="ingreso", categoria="Venta POS", monto=total,
        descripcion=f"Venta {venta.numero_venta}", usuario_nombre=usuario["nombre_completo"],
        referencia=venta.numero_venta,
    ))

    db.commit()
    return JSONResponse({"ok": True, "numero_venta": venta.numero_venta, "total": float(total), "cambio": float(cambio)})
