"""Envío automático de WhatsApp al cliente (usa la API de Twilio). Si no
hay credenciales configuradas en Configuración > Notificaciones, la
función simplemente no hace nada: el aviso manual por WhatsApp (botón
"Avisar por WhatsApp" en la orden) sigue disponible como respaldo y nunca
se ve afectado por esto."""
import logging

logger = logging.getLogger(__name__)


def _telefono_con_codigo_pais(telefono: str) -> str:
    """Limpia el teléfono y le antepone el código de país de Honduras (504)
    si parece un número local de 8 dígitos sin código. Si ya trae código de
    país (más de 8 dígitos) o viene vacío, lo deja tal cual."""
    limpio = "".join(ch for ch in (telefono or "") if ch.isdigit())
    if len(limpio) == 8:
        limpio = "504" + limpio
    return limpio


def enviar_whatsapp(cfg, telefono: str, mensaje: str) -> bool:
    """Intenta mandar `mensaje` por WhatsApp a `telefono` usando las
    credenciales de Twilio guardadas en Configuración. Devuelve True si el
    envío se aceptó, False si no hay credenciales configuradas, si el
    envío automático está desactivado, si no hay teléfono válido, o si
    Twilio devolvió un error (nunca lanza una excepción: un problema con
    Twilio no debe impedir que se guarde el cambio de estado de la
    orden)."""
    if not cfg or not cfg.notificar_whatsapp_automatico:
        return False
    if not (cfg.twilio_account_sid and cfg.twilio_auth_token and cfg.twilio_whatsapp_from):
        return False

    telefono_limpio = _telefono_con_codigo_pais(telefono)
    if not telefono_limpio:
        return False

    remitente = cfg.twilio_whatsapp_from.strip()
    if not remitente.startswith("whatsapp:"):
        remitente = "whatsapp:" + remitente

    try:
        from twilio.rest import Client

        client = Client(cfg.twilio_account_sid, cfg.twilio_auth_token)
        client.messages.create(
            from_=remitente,
            to="whatsapp:+" + telefono_limpio,
            body=mensaje,
        )
        return True
    except Exception:
        logger.exception("No se pudo enviar el WhatsApp automático al cliente (teléfono=%s)", telefono)
        return False
