@echo off
setlocal

echo ===============================================
echo    INICIANDO CARGA DE DATOS DE PRUEBA
echo ===============================================

REM Llama al comando de gestion de Django: python manage.py seed
python manage.py seed

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] La carga de datos ha fallado.
    echo.
) else (
    echo.
    echo ✅ La carga de datos de prueba ha finalizado exitosamente.
    echo.
)

pause
endlocal