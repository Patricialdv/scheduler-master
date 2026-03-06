@echo off
title Automatic-Scheduler - Desarrollo Rapido
echo ===============================================
echo    MODO DESARROLLO RAPIDO
echo ===============================================
echo.
echo Asumiendo que la base de datos ya esta ejecutandose
echo.

echo Iniciando servidor Django...
python manage.py runserver

echo ===============================================
echo    DESARROLLO RAPIDO INICIADO
echo ===============================================
echo.
pause