# Sistema de Taller de Reparación

Sistema web completo para administrar un taller de reparación de celulares,
tablets, computadoras y otros equipos: órdenes de servicio, clientes,
técnicos, inventario, punto de venta, contabilidad, reportes, PDF y acceso
por QR desde el celular.

Construido con **Python + FastAPI + SQLAlchemy + Jinja2**. Funciona con
**SQLite** en desarrollo local y con **PostgreSQL** en producción (Railway),
usando la misma base de código gracias a la variable `DATABASE_URL`.

## 1. Requisitos en Windows

- [Python 3.11 o superior](https://www.python.org/downloads/) (al instalar, marca la casilla "Add python.exe to PATH").
- [Visual Studio Code](https://code.visualstudio.com/).
- Extensión "Python" de Microsoft instalada en VS Code (se instala desde el ícono de extensiones, buscando "Python").

## 2. Cómo correr el sistema en tu PC (paso a paso)

1. Abre **VS Code**.
2. Ve a **Archivo → Abrir carpeta...** y selecciona la carpeta `TallerApp` (esta carpeta, dentro de tus Documentos).
3. Abre una terminal integrada: menú **Terminal → Nueva terminal**.
4. Crea un entorno virtual (solo la primera vez). Escribe y presiona Enter:
   ```
   python -m venv venv
   ```
   Resultado esperado: se crea una carpeta `venv` dentro del proyecto (no aparece nada más en pantalla).
5. Activa el entorno virtual:
   ```
   venv\Scripts\activate
   ```
   Resultado esperado: la línea de la terminal ahora empieza con `(venv)`.
6. Instala las dependencias del proyecto (solo la primera vez, o cuando se agregue una nueva):
   ```
   pip install -r requirements.txt
   ```
   Resultado esperado: al final aparece "Successfully installed ..." con la lista de paquetes.
7. Copia el archivo de variables de entorno de ejemplo:
   ```
   copy .env.example .env
   ```
   Resultado esperado: aparece un nuevo archivo `.env` en el explorador de archivos de VS Code. Puedes abrirlo y cambiar `SECRET_KEY` por cualquier texto largo si quieres, no es obligatorio para probar localmente.
8. Inicia el sistema:
   ```
   python run.py
   ```
   Resultado esperado: en la terminal aparece un mensaje con la URL local (`http://127.0.0.1:8000`) y la URL para el celular.
9. Abre el navegador y entra a: **http://127.0.0.1:8000**
10. Inicia sesión con el usuario administrador que se crea automáticamente la primera vez:
    - Usuario: `admin`
    - Contraseña: `admin123`

   **Importante:** cambia esta contraseña o crea tu propio usuario administrador desde el menú "Usuarios" y desactiva/della el usuario `admin` de ejemplo antes de usar el sistema en producción.

### Si algo falla

- **"python no se reconoce como un comando..."** → Reinstala Python marcando "Add to PATH", o usa `py` en vez de `python`.
- **Error al instalar paquetes (`pip install`)** → Verifica tu conexión a internet y vuelve a intentar. Si un paquete específico falla, copia el mensaje de error completo para revisarlo.
- **"Address already in use" / puerto ocupado** → Ya hay algo usando el puerto 8000. Cierra la otra ventana de terminal que esté corriendo el sistema, o cambia el puerto en `run.py`.
- **La página no carga** → Verifica que la terminal siga mostrando el servidor corriendo (no se haya cerrado con Ctrl+C por accidente).

## 3. Acceder desde el celular (misma red Wi-Fi)

1. Con el sistema corriendo (`python run.py`), entra a **Configuración → Acceso QR** dentro del sistema.
2. Escanea el código QR con la cámara del celular (debe estar conectado a la misma red Wi-Fi que la PC).
3. Si cambias de red, recarga esa página para obtener el nuevo código.

## 4. Estructura del proyecto

```
TallerApp/
├── app/
│   ├── main.py            # Arranque de la aplicación FastAPI
│   ├── config.py          # Configuración desde variables de entorno
│   ├── database.py        # Conexión SQLite/PostgreSQL (usa DATABASE_URL)
│   ├── models.py          # Tablas de la base de datos (SQLAlchemy)
│   ├── schemas.py         # Esquemas para los endpoints JSON (POS)
│   ├── security.py        # Hash de contraseñas y sesión
│   ├── deps.py             # Login requerido / roles requeridos
│   ├── templates_env.py    # Plantillas Jinja2 compartidas (filtros, etc.)
│   ├── routers/             # Una ruta por módulo: clientes, ordenes, pos...
│   ├── templates/            # Vistas HTML (Jinja2)
│   ├── static/                # CSS, JavaScript
│   └── utils/                  # PDF, QR, cálculos financieros, numeración
├── alembic/                     # Migraciones de base de datos
├── requirements.txt
├── run.py                        # Forma sencilla de arrancar en Windows
├── Procfile                       # Comando de arranque para Railway
└── .env.example
```

## 5. Usuario y roles

- **Administrador**: acceso total, incluyendo usuarios, técnicos y configuración.
- **Técnico** y **Vendedor**: acceso operativo (órdenes, clientes, inventario, POS, contabilidad, reportes), sin poder gestionar usuarios/técnicos ni cambiar la configuración del taller.

## 6. Base de datos: SQLite (local) y PostgreSQL (Railway)

No hay que tocar el código para cambiar de motor de base de datos: todo se
controla con la variable de entorno `DATABASE_URL`.

- Local (por defecto): `sqlite:///./taller.db`
- Railway: Railway la define automáticamente al agregar el plugin de PostgreSQL.

Las tablas se crean/actualizan automáticamente al iniciar la aplicación,
ejecutando las migraciones de Alembic (`alembic/versions/`). Si en el futuro
se agregan nuevos campos o tablas, se debe generar una nueva migración en vez
de borrar la base de datos.

## 7. Despliegue en Railway (GitHub + PostgreSQL + URL pública)

Ver la guía paso a paso que te dio Claude en la conversación. En resumen:

1. Subir este proyecto a un repositorio de GitHub.
2. Crear un proyecto en Railway y conectarlo a ese repositorio.
3. Agregar el plugin de PostgreSQL dentro del proyecto de Railway.
4. Configurar la variable de entorno `SECRET_KEY` (Railway define `DATABASE_URL` solo).
5. Esperar el deploy y revisar los logs.
6. Generar el dominio público desde la pestaña "Settings" del servicio.
7. Entrar a la URL pública y verificar que el login funcione y los datos se guarden.

## 8. Comandos útiles

```
venv\Scripts\activate          # Activar entorno virtual
python run.py                  # Correr el sistema localmente
pip install -r requirements.txt  # Instalar/actualizar dependencias
python -m alembic revision --autogenerate -m "descripcion del cambio"  # Nueva migración
python -m alembic upgrade head   # Aplicar migraciones pendientes
```
