@echo off
title Automatic-Scheduler - Desarrollo Completo
echo ===============================================
echo    INICIANDO ENTORNO DE DESARROLLO COMPLETO
echo ===============================================
echo.

echo [1/3] Levantando base de datos PostgreSQL...
docker-compose up -d scheduler-db pgadmin
if errorlevel 1 (
    echo ERROR: No se pudo levantar la base de datos
    pause
    exit /b 1
)

echo [2/3] Esperando a que la base de datos este lista...
echo Esperando 10 segundos para inicializacion de BD...
timeout /t 10 /nobreak >nul

echo [3/3] Iniciando servidor Django...
python manage.py runserver

echo ===============================================
echo    ENTORNO INICIADO CORRECTAMENTE
echo ===============================================
echo.
echo Servidor Django disponible en: http://localhost:8000
echo.
pause