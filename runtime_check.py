# Script simple para confirmar que el entorno tiene las dependencias instaladas.
import importlib
faltantes = []
for m in ["fastapi", "uvicorn", "sqlalchemy", "jinja2", "reportlab", "qrcode", "bcrypt", "alembic", "psycopg2"]:
    try:
        importlib.import_module(m)
    except ImportError:
        faltantes.append(m)
if faltantes:
    print("Faltan instalar:", ", ".join(faltantes))
else:
    print("Todas las dependencias estan instaladas correctamente.")
