@echo off
echo ===============================================
echo    BUILD DE PRODUCCION
echo ===============================================
echo.

echo [1/4] Verificando dependencias...
call python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Fallo en la instalacion de dependencias
    pause
    exit /b 1
)

echo [2/4] Aplicando migraciones...
python manage.py migrate
if errorlevel 1 (
    echo ERROR: Fallo en migraciones
    pause
    exit /b 1
)

echo [3/4] Recogiendo archivos estáticos...
python manage.py collectstatic --noinput
if errorlevel 1 (
    echo ERROR: Fallo al recoger archivos estáticos
    pause
    exit /b 1
)

echo [4/4] Construyendo imagen Docker...
docker build -t django-app:latest .
if errorlevel 1 (
    echo ERROR: Fallo en la construccion de Docker
    pause
    exit /b 1
)

echo ===============================================
echo    BUILD DE PRODUCCION COMPLETADO!
echo ===============================================
echo Imagen creada: django-app:latest
echo.
echo Para ejecutar: docker run -p 8000:8000 --env-file .env django-app:latest
echo.
pause