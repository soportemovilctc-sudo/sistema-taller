"""Endpoints JSON de apoyo: búsqueda global rápida y resumen para el
asistente panda (usuario de Caja)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.database import get_db
from app.models import OrdenServicio, Cliente, Configuracion
from app.deps import login_required

router = APIRouter()


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
    llevan más días de la cuenta sin entregarse. Usa exactamente la misma
    regla que ya existe en el Dashboard y en el filtro "Vencidas" de
    Órdenes (config.dias_vencido_alerta, por defecto 3), para no inventar
    un criterio nuevo de "vencida"."""
    cfg = db.get(Configuracion, 1)
    umbral = cfg.dias_vencido_alerta if cfg else 3

    activas = db.query(OrdenServicio).filter(
        OrdenServicio.estado.notin_(["ENTREGADO", "CANCELADO"])
    ).all()
    vencidas = sorted(
        [o for o in activas if o.dias_en_taller() >= umbral],
        key=lambda o: o.dias_en_taller(), reverse=True,
    )

    return {
        "umbral_dias": umbral,
        "vencidas_total": len(vencidas),
        "vencidas_detalle": [
            {"numero_orden": o.numero_orden, "dias": o.dias_en_taller()}
            for o in vencidas[:5]
        ],
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
def panda_frases_frecuentes(db: Session = Depends(get_db), usuario=Depends(login_required)):
    """Frases de 'Falla reportada' más usadas antes en el taller, para
    sugerirlas como autorelleno al describir el problema de una orden
    nueva."""
    filas = (
        db.query(OrdenServicio.falla_reportada, func.count(OrdenServicio.id).label("n"))
        .filter(OrdenServicio.falla_reportada.isnot(None), OrdenServicio.falla_reportada != "")
        .group_by(OrdenServicio.falla_reportada)
        .order_by(func.count(OrdenServicio.id).desc())
        .limit(8)
        .all()
    )
    return {"frases": [f[0] for f in filas]}
