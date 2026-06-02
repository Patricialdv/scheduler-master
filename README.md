# Sistema de generacion y gestion de horarios escolares

## Version 0.01

### Pasos para iniciar el sistema:
1. Instalar Python 3.13
2. Instalar Docker Desktop
3. Crear el archivo .env con los valores:
		`SECRET_KEY=<una clave secreta>`
		`DEBUG=True`

		`DB_NAME=scheduler`
		`DB_USER=scheduler_user`
		`DB_PASSWORD=una_password_segura`
		`DB_HOST=localhost`
		`DB_PORT=5432`

		`PGADMIN_DEFAULT_EMAIL=admin@admin.com`
		`PGADMIN_DEFAULT_PASSWORD=admin123` 
		
4.  Dependencias de python: 
	1. Abrir la carpeta del proyecto en el Visual Studio Code
	2. Abrir una terminal
	3. Crear el entorno virtual con python `-m venv .venv`
	4. Activar el entorno virtual con  `.venv\Scripts\activate`
	5. Ejecutar pip install `-r requirements.txt`
5. Levantar la base de datos ejecutando `docker compose up -d`  en la terminal
6. Aplicar migraciones ejecutando `python manage.py` migrate en la terminal
7. Crear superusuario ejecutando `python manage.py createsuperuser` en la terminal
8. Introducir nombre de usuario y contraseña, al escribir la contraseña no aparecerán los caracteres en pantalla.
9. Ejecutar `./menu` en la terminal y escoger la opción 1
10. Si no hubo errores debe salir esto en la terminal:
	    `Iniciando Desarrollo Completo...`
		`===============================================`
		   `INICIANDO ENTORNO DE DESARROLLO COMPLETO`
		`===============================================`
		
		`[1/3] Levantando base de datos PostgreSQL...`
		`[+] Running 2/2`
		 `✔ Container scheduler-db       Healthy                                                                                                                                                                  0.6s` 
		 `✔ Container scheduler-pgadmin  Running                                                                                                                                                                  0.0s` 
		`[2/3] Esperando a que la base de datos este lista...`
		`Esperando 10 segundos para inicializacion de BD...`
		`[3/3] Iniciando servidor Django...`
		`Watching for file changes with StatReloader`
		`Performing system checks...`
		
		`System check identified no issues (0 silenced).`
		`June 02, 2026 - 17:16:05`
		`Django version 5.2.7, using settings 'config.general.settings'`
		`Starting development server at http://127.0.0.1:8000/`
		`Quit the server with CTRL-BREAK.`
		
		`WARNING: This is a development server. Do not use it in a production           setting. Use a production WSGI or ASGI server instead.`
		`For more information on production servers see: https://docs.djangoproject.com/en/5.2/howto/deployment/`
		
11. Abrir http://127.0.0.1:8000/ en un navegador
12. Para cerrar el sistema cerrarlo en el navegador y ejecutar ctrl+c y luego escoger la opción y