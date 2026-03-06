@echo off
echo Verificando conexion a la base de datos...
for /l %%i in (1,1,30) do (
    timeout /t 2 /nobreak >nul
    python -c "
import sys
try:
    from django.db import connection
    connection.ensure_connection()
    print('Base de datos conectada!')
    sys.exit(0)
except Exception as e:
    print(f'Esperando BD... [%%i/30] - {e}')
    sys.exit(1)
" >nul 2>&1
    if errorlevel 0 (
        echo Base de datos lista!
        exit /b 0
    )
)
echo ERROR: Timeout esperando base de datos
exit /b 1