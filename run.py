"""Forma sencilla de arrancar el sistema en Windows: python run.py

Hace lo mismo que "uvicorn app.main:app --reload" pero además imprime en la
terminal la URL para abrir el sistema desde el celular en la misma red Wi-Fi.
"""
import uvicorn
from app.utils.qr_local import obtener_ip_local

if __name__ == "__main__":
    ip = obtener_ip_local()
    puerto = 8000
    print("=" * 60)
    print(" SISTEMA DE TALLER - iniciando servidor local")
    print("=" * 60)
    print(f" En esta PC:        http://127.0.0.1:{puerto}")
    print(f" Desde el celular:  http://{ip}:{puerto}  (misma red Wi-Fi)")
    print(" El código QR para el celular está en Configuración > Acceso QR.")
    print("=" * 60)
    uvicorn.run("app.main:app", host="0.0.0.0", port=puerto, reload=True)
