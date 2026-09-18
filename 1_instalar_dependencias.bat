@echo off
cd /d "%~dp0"
echo ============================================================
echo  PASO 1: Instalando el Sistema de Taller
echo ============================================================
echo.
echo Creando entorno virtual de Python...
python -m venv venv
if errorlevel 1 (
    echo.
    echo ERROR: no se pudo crear el entorno virtual. Verifica que Python este instalado y en el PATH.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
echo.
echo Instalando dependencias (esto puede tardar 1-3 minutos)...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: fallo la instalacion de dependencias. Revisa el mensaje de arriba.
    pause
    exit /b 1
)
if not exist ".env" (
    copy .env.example .env
    echo Se creo el archivo .env con la configuracion por defecto.
)
echo.
echo ============================================================
echo  INSTALACION COMPLETADA CORRECTAMENTE
echo  Ahora puedes ejecutar "2_iniciar_sistema.bat"
echo ============================================================
pause
