"""Generación de números consecutivos únicos (órdenes, ventas)."""
from sqlalchemy.orm import Session


def siguiente_numero(ultimo_numero, prefijo: str, ancho: int = 6) -> str:
    if not ultimo_numero:
        siguiente = 1
    else:
        try:
            siguiente = int(str(ultimo_numero).split("-")[-1]) + 1
        except (ValueError, IndexError):
            siguiente = 1
    return f"{prefijo}-{str(siguiente).zfill(ancho)}"


def generar_numero_orden(db: Session) -> str:
    from app.models import OrdenServicio
    ultimo = db.query(OrdenServicio).order_by(OrdenServicio.id.desc()).first()
    return siguiente_numero(ultimo.numero_orden if ultimo else None, "OS")


def generar_numero_venta(db: Session) -> str:
    from app.models import Venta
    ultimo = db.query(Venta).order_by(Venta.id.desc()).first()
    return siguiente_numero(ultimo.numero_venta if ultimo else None, "V")


def generar_numero_factura(cfg, tipo: str) -> tuple[str, int]:
    """Genera el siguiente número de documento para una factura, consumiendo
    el correlativo correspondiente en la Configuración de Facturación.
    Muta `cfg` en memoria; quien llama decide cuándo hacer commit.

    Fiscal:  Establecimiento-PuntoEmision-TipoDoc-Correlativo(8 dígitos)
    Interno: PREFIJO-Correlativo(6 dígitos)
    """
    if tipo == "fiscal":
        correlativo = (cfg.correlativo_fiscal_actual or 0) + 1
        cfg.correlativo_fiscal_actual = correlativo
        numero = (
            f"{cfg.establecimiento or '001'}-{cfg.punto_emision or '001'}-"
            f"{cfg.tipo_documento_codigo or '01'}-{str(correlativo).zfill(8)}"
        )
    else:
        correlativo = (cfg.correlativo_interno_actual or 0) + 1
        cfg.correlativo_interno_actual = correlativo
        numero = f"{(cfg.prefijo_interno or 'REC').strip()}-{str(correlativo).zfill(6)}"
    return numero, correlativo


def extraer_correlativo_de_rango(valor_rango: str) -> int | None:
    """Extrae el correlativo numérico final de un número con formato
    000-001-01-00000500 -> 500. Devuelve None si no se puede interpretar."""
    if not valor_rango:
        return None
    try:
        return int(str(valor_rango).split("-")[-1])
    except (ValueError, IndexError):
        return None
