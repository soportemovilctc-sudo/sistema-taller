"""Chat del asistente (mascota): interpreta pedidos cortos en español y,
cuando aplica, sugiere una acción concreta para que el usuario la confirme
con un clic (nunca se ejecuta nada sin esa confirmación). Reutiliza
exactamente la misma lógica que ya usan los formularios normales de
Órdenes (app/routers/ordenes.py: _aplicar_cambio_estado, _aplicar_abono),
para que el resultado sea idéntico sea cual sea el camino que se use.

Cada respuesta de /api/asistente/consulta trae, además del texto y la
acción sugerida (si hay una), dos campos para que el navegador sepa cómo
tratar una respuesta corta del usuario (solo un número) en el siguiente
mensaje, sin que el usuario tenga que repetir todo el pedido:
  - "esperando": "numero_orden" | "monto" | null — qué tipo de dato se le
    pidió al usuario, si se le pidió algo.
  - "intencion_pendiente": la acción que quedó a medias (para que el
    navegador arme el siguiente mensaje completo, ej. "entregar orden 45"
    en vez de mandar solo "45", que por sí solo no dice qué hacer).
"""
from datetime import datetime
from decimal import InvalidOperation

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OrdenServicio
from app.deps import login_required
from app.schemas import AsistenteConsultaIn, AsistenteEjecutarIn
from app.utils.asistente_nlu import interpretar_mensaje
from app.routers.ordenes import _aplicar_cambio_estado, _aplicar_abono

router = APIRouter()


def _respuesta(texto, accion=None, orden_numero_referencia=None, esperando=None, intencion_pendiente=None):
    return {
        "texto": texto, "accion": accion, "orden_numero_referencia": orden_numero_referencia,
        "esperando": esperando, "intencion_pendiente": intencion_pendiente,
    }


def _buscar_orden_por_numero(db: Session, numero_texto: str):
    """Busca una orden por los dígitos que mencionó el usuario: acepta el
    número completo (OS-000045) o solo el consecutivo (45)."""
    digitos = "".join(ch for ch in (numero_texto or "") if ch.isdigit())
    if not digitos:
        return None
    orden = db.query(OrdenServicio).filter(
        OrdenServicio.numero_orden.ilike(f"%-{digitos.zfill(6)}")
    ).first()
    if not orden:
        orden = db.query(OrdenServicio).filter(
            OrdenServicio.numero_orden.ilike(f"%{digitos}")
        ).order_by(OrdenServicio.id.desc()).first()
    return orden


@router.post("/api/asistente/consulta")
def asistente_consulta(body: AsistenteConsultaIn, db: Session = Depends(get_db), usuario=Depends(login_required)):
    resultado = interpretar_mensaje(body.mensaje)
    intencion = resultado["intencion"]

    if intencion == "conversacion":
        return _respuesta(resultado["texto"], orden_numero_referencia=body.contexto_orden)

    if intencion == "desconocido":
        return _respuesta(
            "No entendí bien ese pedido. Puedo: marcar una orden como entregada, avisar que ya se notificó al cliente, o registrar un abono. "
            "Por ejemplo: “marca la orden 45 como entregada”.",
            orden_numero_referencia=body.contexto_orden,
        )

    numero_mencionado = resultado.get("numero_orden") or body.contexto_orden
    if not numero_mencionado:
        return _respuesta(
            "¿De qué orden hablas? Dime el número, por ejemplo “la 45” u “OS-000045”.",
            esperando="numero_orden", intencion_pendiente=intencion,
        )

    orden = _buscar_orden_por_numero(db, numero_mencionado)
    if not orden:
        return _respuesta(
            f"No encontré ninguna orden con el número {numero_mencionado}. ¿Me das el número correcto?",
            esperando="numero_orden", intencion_pendiente=intencion,
        )

    if intencion == "marcar_entregado":
        if orden.estado == "ENTREGADO":
            return _respuesta(f"La orden {orden.numero_orden} ya está marcada como ENTREGADO.", orden_numero_referencia=orden.numero_orden)
        if orden.estado == "CANCELADO":
            return _respuesta(f"La orden {orden.numero_orden} está CANCELADO, no se puede marcar como entregada.", orden_numero_referencia=orden.numero_orden)
        aviso_saldo = (
            f" Tiene un saldo de L {float(orden.saldo):.2f} que quedaría registrado como pagado automáticamente."
            if orden.saldo and orden.saldo > 0 else ""
        )
        equipo = f"{orden.marca or ''} {orden.modelo or ''}".strip()
        return _respuesta(
            f"¿Marco la orden {orden.numero_orden}{' (' + equipo + ')' if equipo else ''} como ENTREGADO?{aviso_saldo}",
            accion={"tipo": "marcar_entregado", "orden_id": orden.id, "parametros": {}, "etiqueta": "Sí, marcar como entregada"},
            orden_numero_referencia=orden.numero_orden,
        )

    if intencion == "marcar_notificado":
        if orden.estado != "LISTO PARA ENTREGAR":
            return _respuesta(f"La orden {orden.numero_orden} no está en estado LISTO PARA ENTREGAR (está en {orden.estado}).", orden_numero_referencia=orden.numero_orden)
        if orden.notificado_listo:
            return _respuesta(f"La orden {orden.numero_orden} ya estaba marcada como avisada.", orden_numero_referencia=orden.numero_orden)
        return _respuesta(
            f"¿Marco la orden {orden.numero_orden} como que ya se avisó al cliente?",
            accion={"tipo": "marcar_notificado", "orden_id": orden.id, "parametros": {}, "etiqueta": "Sí, ya se avisó"},
            orden_numero_referencia=orden.numero_orden,
        )

    if intencion == "registrar_abono":
        if orden.estado == "CANCELADO":
            return _respuesta(f"La orden {orden.numero_orden} está CANCELADO, no se le puede registrar un abono.", orden_numero_referencia=orden.numero_orden)
        if not orden.saldo or orden.saldo <= 0:
            return _respuesta(f"La orden {orden.numero_orden} no tiene saldo pendiente.", orden_numero_referencia=orden.numero_orden)
        monto = resultado.get("monto")
        if not monto:
            return _respuesta(
                f"¿De cuánto es el abono para la orden {orden.numero_orden}? (saldo pendiente: L {float(orden.saldo):.2f})",
                orden_numero_referencia=orden.numero_orden, esperando="monto", intencion_pendiente="registrar_abono",
            )
        if monto > float(orden.saldo):
            return _respuesta(
                f"Ese monto (L {monto:.2f}) es mayor al saldo pendiente de la orden {orden.numero_orden} (L {float(orden.saldo):.2f}).",
                orden_numero_referencia=orden.numero_orden, esperando="monto", intencion_pendiente="registrar_abono",
            )
        return _respuesta(
            f"¿Registro un abono de L {monto:.2f} a la orden {orden.numero_orden}?",
            accion={"tipo": "registrar_abono", "orden_id": orden.id, "parametros": {"monto": monto}, "etiqueta": "Sí, registrar el abono"},
            orden_numero_referencia=orden.numero_orden,
        )

    return _respuesta("No pude procesar ese pedido.", orden_numero_referencia=body.contexto_orden)


@router.post("/api/asistente/ejecutar")
def asistente_ejecutar(body: AsistenteEjecutarIn, db: Session = Depends(get_db), usuario=Depends(login_required)):
    """Ejecuta una acción que el usuario ya confirmó en el chat. Vuelve a
    validar todo del lado del servidor (nunca confía en lo que mandó el
    navegador): el estado de la orden pudo haber cambiado entre que se
    sugirió la acción y que se confirmó."""
    orden = db.get(OrdenServicio, body.orden_id)
    if not orden:
        return {"ok": False, "texto": "Esa orden ya no existe."}

    if body.tipo == "marcar_entregado":
        if orden.estado in ("ENTREGADO", "CANCELADO"):
            return {"ok": False, "texto": f"La orden {orden.numero_orden} ya no se puede marcar como entregada (está {orden.estado})."}
        monto_pago_automatico = _aplicar_cambio_estado(db, orden, "ENTREGADO", "Marcado desde el asistente", usuario["nombre_completo"])
        db.commit()
        texto = f"¡Listo! Orden {orden.numero_orden} marcada como ENTREGADO."
        if monto_pago_automatico:
            texto += f" Se registró un pago automático de L {float(monto_pago_automatico):.2f} para saldar la orden."
        return {"ok": True, "texto": texto}

    if body.tipo == "marcar_notificado":
        if orden.estado != "LISTO PARA ENTREGAR" or orden.notificado_listo:
            return {"ok": False, "texto": "Esa orden ya no aplica para marcarse como avisada."}
        orden.notificado_listo = True
        orden.fecha_notificado_listo = datetime.utcnow()
        db.commit()
        return {"ok": True, "texto": f"Listo, orden {orden.numero_orden} marcada como avisada al cliente."}

    if body.tipo == "registrar_abono":
        monto = body.parametros.get("monto")
        if orden.estado == "CANCELADO" or not orden.saldo or orden.saldo <= 0 or not monto:
            return {"ok": False, "texto": "Ese abono ya no se puede registrar (revisa el saldo de la orden)."}
        try:
            monto_validado = _aplicar_abono(db, orden, str(monto), orden.forma_pago or "Efectivo", "Abono registrado desde el asistente", usuario["nombre_completo"])
        except (ValueError, InvalidOperation) as e:
            return {"ok": False, "texto": str(e)}
        db.commit()
        return {"ok": True, "texto": f"¡Listo! Abono de L {float(monto_validado):.2f} registrado en la orden {orden.numero_orden}."}

    return {"ok": False, "texto": "No reconozco ese tipo de acción."}
