@echo off
rem USO LOCAL UNICAMENTE.
rem Wrapper local para pruebas sobre PostgreSQL Vexxo; no usar en produccion.
call "%~dp0run_manage_vexxo_app.cmd" test finance.transactions.tests --verbosity 2 --keepdb
exit /b %ERRORLEVEL%
