@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo ============================================================
echo  Iniciando el Sistema de Taller...
echo  Usuario:    admin
echo  Contrasena: admin123
echo  (Cambia esta contrasena luego desde Usuarios)
echo ============================================================
python run.py
pause
