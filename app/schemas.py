"""Esquemas Pydantic usados por los endpoints JSON (POS, búsqueda, AJAX)."""
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional


class ItemCarritoIn(BaseModel):
    producto_id: int
    cantidad: int = Field(gt=0)
    # Precio unitario opcional: si viene y es mayor a 0, reemplaza el
    # precio_venta del producto para esa línea (permite que quien cobra
    # ajuste el precio de venta de un repuesto en el momento, igual que ya
    # se puede hacer al agregar un repuesto a una orden de servicio).
    precio_unitario: Optional[Decimal] = Field(default=None, ge=0)


class VentaIn(BaseModel):
    items: list[ItemCarritoIn]
    descuento: Decimal = Decimal("0")
    forma_pago: str = "Efectivo"
    monto_recibido: Decimal = Decimal("0")
    cliente_id: Optional[int] = None


class VentaOut(BaseModel):
    ok: bool
    numero_venta: str | None = None
    total: float | None = None
    cambio: float | None = None
    mensaje: str | None = None
    factura_id: int | None = None
    numero_documento: str | None = None


class AsistenteConsultaIn(BaseModel):
    mensaje: str
    contexto_orden: str | None = None


class AsistenteEjecutarIn(BaseModel):
    tipo: str
    orden_id: int
    parametros: dict = {}
