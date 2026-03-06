@echo off
echo ===============================================
echo    GESTION DE MIGRACIONES DE BASE DE DATOS
echo ===============================================
echo.
echo 1. Crear nuevas migraciones
echo 2. Aplicar migraciones pendientes
echo 3. Ver estado de migraciones
echo 4. Resetear base de datos (CUIDADO!)
echo.
set /p choice="Selecciona una opcion (1-4): "

if "%choice%"=="1" (
    python manage.py makemigrations
) else if "%choice%"=="2" (
    python manage.py migrate
) else if "%choice%"=="3" (
    python manage.py showmigrations
) else if "%choice%"=="4" (
    echo ESTA ACCION ELIMINARA TODOS LOS DATOS!
    set /p confirm="¿Estas seguro? (si/no): "
    if /i "%confirm%"=="si" (
        echo Eliminando base de datos...
        docker-compose down -v
        echo Volumenes eliminados. Levantando base de datos...
        docker-compose up -d scheduler-db
        timeout /t 10 /nobreak >nul
        echo Aplicando migraciones...
        python manage.py migrate
        echo ¿Desea crear un superusuario? (si/no)
        set /p superuser=
        if /i "%superuser%"=="si" (
            python manage.py createsuperuser
        )
    )
) else (
    echo Opcion no valida
)

pause