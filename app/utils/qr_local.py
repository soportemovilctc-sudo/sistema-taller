"""Generación del QR de acceso local (misma red Wi-Fi) y detección de IP."""
import io
import socket
import qrcode


def obtener_ip_local() -> str:
    """Detecta la IP local de la máquina en la red (no la de loopback)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No se envía tráfico real; solo se usa para que el SO elija la interfaz correcta.
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def generar_qr_png(texto: str) -> bytes:
    img = qrcode.make(texto)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def url_acceso_local(puerto: int = 8000) -> str:
    return f"http://{obtener_ip_local()}:{puerto}"
