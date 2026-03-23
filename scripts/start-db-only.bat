@echo off
title Automatic-Scheduler - Solo Base de Datos
echo ===============================================
echo    INICIANDO SOLO BASE DE DATOS
echo ===============================================
echo.

docker-compose up -d scheduler-db pgadmin

echo Base de datos iniciada!
echo PostgreSQL disponible en: http://localhost:4001
echo PGAdmin disponible en: http://localhost:8081
echo.
echo Presiona cualquier tecla para ver logs...
echo.
echo Credenciales PGAdmin:
echo Email: admin@admin.com
echo Password: admin123
echo.
echo Presiona cualquier tecla para ver logs...
pause
docker-compose logs -f scheduler-db