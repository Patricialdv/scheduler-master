@echo off
echo ===============================================
echo    CONFIGURACION INICIAL DE DESARROLLO
echo ===============================================
echo.

echo [1/4] Instalando dependencias Python...
call python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Fallo en la instalacion de dependencias
    pause
    exit /b 1
)

echo [2/4] Levantando base de datos...
docker-compose up -d scheduler-db
if errorlevel 1 (
    echo ERROR: No se pudo levantar la base de datos
    pause
    exit /b 1
)

echo [3/4] Esperando a que la base de datos este lista...
echo Esperando 10 segundos para inicializacion de BD...
timeout /t 10 /nobreak >nul

echo [4/4] Aplicando migraciones y creando superusuario...
python manage.py migrate
if errorlevel 1 (
    echo ERROR: Fallo al aplicar migraciones
    pause
    exit /b 1
)

echo ¿Desea crear un superusuario? (si/no)
set /p superuser=
if /i "%superuser%"=="si" (
    python manage.py createsuperuser
)

echo ===============================================
echo    CONFIGURACION COMPLETADA!
echo ===============================================
pause