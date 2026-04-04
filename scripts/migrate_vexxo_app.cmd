@echo off
rem USO LOCAL UNICAMENTE.
rem Wrapper local para PostgreSQL Vexxo; no es un artefacto de produccion.
call "%~dp0run_manage_vexxo_app.cmd" migrate --noinput
exit /b %ERRORLEVEL%
