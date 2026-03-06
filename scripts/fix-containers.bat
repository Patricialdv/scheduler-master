@echo off
echo ===============================================
echo    REPARACION DE CONTENEDORES DOCKER
echo ===============================================
echo.

echo [1/4] Deteniendo contenedores conflictivos...
docker stop scheduler-postgres automatic-scheduler-db >nul 2>&1
echo Contenedores detenidos.

echo [2/4] Eliminando contenedores...
docker rm scheduler-postgres automatic-scheduler-db >nul 2>&1
echo Contenedores eliminados.

echo [3/4] Limpiando recursos no utilizados...
docker network prune -f >nul 2>&1
echo Redes limpiadas.

echo [4/4] Verificando estado...
docker-compose ps
echo.
echo Reparacion completada. Ahora ejecuta 'Desarrollo Completo' nuevamente.
pause