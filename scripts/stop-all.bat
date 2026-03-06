@echo off
echo ===============================================
echo    DETENIENDO ENTORNO DE DESARROLLO
echo ===============================================
echo.

echo Deteniendo contenedores...
docker-compose down

echo ===============================================
echo    ENTORNO DETENIDO CORRECTAMENTE
echo ===============================================
pause