"""Punto de venta (POS): carrito, cálculo de totales, cobro y descuento de inventario."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.templates_env import templates
from app.database import get_db
from app.models import (
    Producto, Venta, DetalleVenta, MovimientoInventario, MovimientoFinanciero, Cliente,
    ConfiguracionFacturacion, Factura,
)
from app.schemas import VentaIn
from app.utils.numbering import generar_numero_venta, generar_numero_factura
from app.utils.calculations import to_decimal, aplicar_impuesto
from app.utils.libro_diario import registrar_asiento_para_movimiento
from app.deps import login_required

router = APIRouter()


def _cfg_facturacion(db: Session) -> ConfiguracionFacturacion:
    cfg = db.get(ConfiguracionFacturacion, 1)
    if not cfg:
        cfg = ConfiguracionFacturacion(id=1)
        db.add(cfg)
        db.flush()
    return cfg


def _isv_tasa(db: Session) -> Decimal:
    cfg = db.get(ConfiguracionFacturacion, 1)
    if cfg and cfg.isv_tasa is not None:
        return to_decimal(cfg.isv_tasa)
    return to_decimal(15)


@router.get("/pos")
def pos_index(request: Request, db: Session = Depends(get_db), usuario=Depends(login_required)):
    productos = db.query(Producto).filter(Producto.estado == "activo", Producto.existencia > 0).order_by(Producto.nombre).all()
    clientes = db.query(Cliente).order_by(Cliente.nombre).all()
    return templates.TemplateResponse("pos/index.html", {
        "request": request, "productos": productos, "clientes": clientes, "usuario": usuario,
        "tasa_isv": _isv_tasa(db),
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
        # Si viene un precio_unitario (el cajero lo ajustó en el carrito), se
        # usa ese en vez del precio_venta del catálogo, igual que ya se
        # permite al agregar un repuesto a una orden de servicio.
        if item.precio_unitario is not None and item.precio_unitario > 0:
            precio = to_decimal(item.precio_unitario)
        else:
            precio = to_decimal(producto.precio_venta)
        sub = (precio * item.cantidad).quantize(Decimal("0.01"))
        subtotal += sub
        detalles.append((producto, item.cantidad, precio, sub))

    descuento = to_decimal(venta_in.descuento)
    if descuento < 0 or descuento > subtotal:
        return JSONResponse({"ok": False, "mensaje": "El descuento no es válido."}, status_code=400)

    total_neto = (subtotal - descuento).quantize(Decimal("0.01"))
    tasa = _isv_tasa(db)
    total = aplicar_impuesto(total_neto, tasa)
    isv_monto = (total - total_neto).quantize(Decimal("0.01"))
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

    mov_venta = MovimientoFinanciero(
        tipo="ingreso", categoria="Venta POS", monto=total,
        descripcion=f"Venta {venta.numero_venta}", usuario_nombre=usuario["nombre_completo"],
        referencia=venta.numero_venta,
    )
    db.add(mov_venta)
    db.flush()
    registrar_asiento_para_movimiento(db, mov_venta, monto_neto=total_neto, isv_monto=isv_monto)

    # Recibo automático: cada venta del Punto de Venta genera de una vez un
    # comprobante interno (no fiscal) para que el cliente se lleve constancia
    # de su compra, sin necesidad de un paso aparte. Si más adelante el
    # cliente necesita una factura fiscal, se puede emitir esa por separado
    # desde Facturas (igual que con las órdenes de servicio).
    cfg_fact = _cfg_facturacion(db)
    numero_documento, correlativo = generar_numero_factura(cfg_fact, "interno")
    cliente_venta = db.get(Cliente, venta.cliente_id) if venta.cliente_id else None
    recibo = Factura(
        venta_id=venta.id,
        tipo="interno",
        numero_documento=numero_documento,
        correlativo=correlativo,
        cliente_nombre=cliente_venta.nombre if cliente_venta else "Consumidor final",
        cliente_rtn=(cliente_venta.rtn or "") if cliente_venta else "",
        cliente_direccion=(cliente_venta.direccion or "") if cliente_venta else "",
        fecha_emision=datetime.utcnow(),
        subtotal=subtotal,
        descuento=descuento,
        importe_exento=Decimal("0.00"),
        importe_gravado=total_neto,
        isv_tasa=tasa,
        isv_monto=isv_monto,
        total=total,
        usuario_nombre=usuario["nombre_completo"],
    )
    db.add(recibo)
    db.flush()

    db.commit()
    return JSONResponse({
        "ok": True, "numero_venta": venta.numero_venta,
        "total": float(total), "isv": float(isv_monto), "cambio": float(cambio),
        "factura_id": recibo.id, "numero_documento": recibo.numero_documento,
    })
