"""Esquemas Pydantic usados por los endpoints JSON (POS, búsqueda, AJAX)."""
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional


class ItemCarritoIn(BaseModel):
    producto_id: int
    cantidad: int = Field(gt=0)


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
