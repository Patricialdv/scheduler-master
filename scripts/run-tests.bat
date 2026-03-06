@echo off
echo ===============================================
echo    EJECUTANDO TESTS
echo ===============================================
echo.

echo [1/3] Verificando que la base de datos este corriendo...
docker-compose up -d scheduler-db

echo [2/3] Esperando inicializacion de BD...
timeout /t 10 /nobreak >nul

echo [3/3] Ejecutando tests...
python manage.py test

if errorlevel 1 (
    echo ===============================================
    echo    TESTS FALLIDOS!
    echo ===============================================
) else (
    echo ===============================================
    echo    TESTS EXITOSOS!
    echo ===============================================
)

pause