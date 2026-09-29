"""Endpoints JSON de apoyo: búsqueda global rápida y resumen para el
asistente panda (usuario de Caja)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.database import get_db
from app.models import OrdenServicio, Cliente, Configuracion, Producto, HistorialEstado, Pago
from app.deps import login_required

router = APIRouter()

# Campos de texto libre donde tiene sentido sugerir frases usadas antes
# (autorrelleno). "observacion" vive en dos tablas distintas según el
# formulario (cambiar estado / registrar abono), por eso son dos entradas
# separadas aunque en la interfaz se vean como el mismo tipo de campo.
CAMPOS_FRECUENTES = {
    "falla_reportada": OrdenServicio.falla_reportada,
    "diagnostico": OrdenServicio.diagnostico,
    "trabajo_realizado": OrdenServicio.trabajo_realizado,
    "observaciones": OrdenServicio.observaciones,
    "observaciones_condicion": OrdenServicio.observaciones_condicion,
    "historial_observacion": HistorialEstado.observacion,
    "pago_observacion": Pago.observacion,
}


@router.get("/api/buscar")
def buscar_global(q: str = "", db: Session = Depends(get_db), usuario=Depends(login_required)):
    if not q or len(q) < 2:
        return {"ordenes": [], "clientes": []}

    like = f"%{q}%"
    ordenes = db.query(OrdenServicio).join(Cliente).filter(or_(
        OrdenServicio.numero_orden.ilike(like), OrdenServicio.imei.ilike(like),
        OrdenServicio.numero_serie.ilike(like), OrdenServicio.marca.ilike(like),
        OrdenServicio.modelo.ilike(like), OrdenServicio.estado.ilike(like),
        Cliente.nombre.ilike(like), Cliente.telefono.ilike(like),
        Cliente.whatsapp.ilike(like), Cliente.dni.ilike(like),
    )).limit(10).all()

    clientes = db.query(Cliente).filter(or_(
        Cliente.nombre.ilike(like), Cliente.telefono.ilike(like), Cliente.dni.ilike(like),
    )).limit(10).all()

    return {
        "ordenes": [{"id": o.id, "numero_orden": o.numero_orden, "cliente": o.cliente.nombre if o.cliente else "",
                     "estado": o.estado, "equipo": f"{o.marca} {o.modelo}".strip()} for o in ordenes],
        "clientes": [{"id": c.id, "nombre": c.nombre, "telefono": c.telefono} for c in clientes],
    }


@router.get("/api/panda/resumen")
def panda_resumen(db: Session = Depends(get_db), usuario=Depends(login_required)):
    """Resumen liviano para el asistente panda: cuántas órdenes activas ya
    llevan más días de la cuenta sin entregarse (usa exactamente la misma
    regla que ya existe en el Dashboard y en el filtro "Vencidas" de
    Órdenes, config.dias_vencido_alerta, por defecto 3, para no inventar
    un criterio nuevo de "vencida"), más otras tres cosas que vale la pena
    recordar de vez en cuando sin que el usuario tenga que preguntar:
    productos con stock bajo, órdenes ya entregadas con saldo pendiente de
    cobrar, y órdenes listas para entregar que todavía no se le avisaron
    al cliente."""
    cfg = db.get(Configuracion, 1)
    umbral = cfg.dias_vencido_alerta if cfg else 3

    activas = db.query(OrdenServicio).filter(
        OrdenServicio.estado.notin_(["ENTREGADO", "CANCELADO"])
    ).all()
    vencidas = sorted(
        [o for o in activas if o.dias_en_taller() >= umbral],
        key=lambda o: o.dias_en_taller(), reverse=True,
    )

    productos_activos = db.query(Producto).filter(Producto.estado == "activo").all()
    stock_bajo_total = sum(1 for p in productos_activos if p.existencia <= p.stock_minimo)

    entregadas_con_saldo = db.query(OrdenServicio).filter(
        OrdenServicio.estado == "ENTREGADO", OrdenServicio.saldo > 0
    ).all()

    listas_sin_avisar_total = db.query(OrdenServicio).filter(
        OrdenServicio.estado == "LISTO PARA ENTREGAR", OrdenServicio.notificado_listo.is_(False)
    ).count()

    return {
        "umbral_dias": umbral,
        "vencidas_total": len(vencidas),
        "vencidas_detalle": [
            {"numero_orden": o.numero_orden, "dias": o.dias_en_taller()}
            for o in vencidas[:5]
        ],
        "stock_bajo_total": stock_bajo_total,
        "saldo_pendiente_total": len(entregadas_con_saldo),
        "saldo_pendiente_monto": float(sum((o.saldo or 0) for o in entregadas_con_saldo)),
        "listas_sin_avisar_total": listas_sin_avisar_total,
    }


@router.get("/api/panda/cliente/{cliente_id}")
def panda_cliente_info(cliente_id: int, db: Session = Depends(get_db), usuario=Depends(login_required)):
    """Resumen rápido de un cliente para mostrar en cuanto la cajera lo
    selecciona en Nueva Orden o en el Punto de Venta: cuántas órdenes tiene
    y si debe saldo pendiente de alguna anterior (no cuenta las
    canceladas)."""
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        return {"encontrado": False}
    ordenes = db.query(OrdenServicio).filter(OrdenServicio.cliente_id == cliente_id).all()
    saldo_pendiente = sum(
        (o.saldo or 0) for o in ordenes if o.estado != "CANCELADO"
    )
    return {
        "encontrado": True,
        "nombre": cliente.nombre,
        "telefono": cliente.telefono or "",
        "whatsapp": cliente.whatsapp or "",
        "ordenes_total": len(ordenes),
        "saldo_pendiente": float(saldo_pendiente),
    }


@router.get("/api/panda/frases-frecuentes")
def panda_frases_frecuentes(campo: str = "falla_reportada", db: Session = Depends(get_db), usuario=Depends(login_required)):
    """Frases más usadas antes en un campo de texto libre del taller
    (falla reportada, diagnóstico, trabajo realizado, observaciones...),
    para sugerirlas como autorelleno. `campo` debe ser una de las claves
    de CAMPOS_FRECUENTES; si mandan cualquier otra cosa (o nada), se usa
    "falla_reportada" por defecto en vez de fallar, para no depender de
    que el frontend siempre mande un valor válido."""
    columna = CAMPOS_FRECUENTES.get(campo, CAMPOS_FRECUENTES["falla_reportada"])
    filas = (
        db.query(columna, func.count(columna).label("n"))
        .filter(columna.isnot(None), columna != "")
        .group_by(columna)
        .order_by(func.count(columna).desc())
        .limit(8)
        .all()
    )
    return {"frases": [f[0] for f in filas]}
