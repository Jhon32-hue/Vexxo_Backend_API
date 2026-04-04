@echo off
rem USO LOCAL UNICAMENTE.
rem No ejecutar en produccion, Cloud Run, CI/CD de despliegue ni entornos cloud.
setlocal

set "ROOT=%~dp0.."
pushd "%ROOT%" >nul

if not defined VEXXO_APP_DB_PASSWORD (
  echo [Vexxo_app] Falta la variable VEXXO_APP_DB_PASSWORD.
  echo.
  echo PowerShell:
  echo   $env:VEXXO_APP_DB_PASSWORD='tu_password'
  echo   .\scripts\run_manage_vexxo_app.cmd migrate --noinput
  echo.
  popd >nul
  exit /b 1
)

set "ENV=local"
set "DB_ENGINE=django.db.backends.postgresql"
set "DB_NAME=Vexxo"
set "DB_USER=postgres"
set "DB_PASSWORD=%VEXXO_APP_DB_PASSWORD%"
set "DB_HOST=127.0.0.1"
set "DB_PORT=5432"
set "DEBUG=False"

if not "%VEXXO_APP_DB_NAME%"=="" set "DB_NAME=%VEXXO_APP_DB_NAME%"
if not "%VEXXO_APP_DB_USER%"=="" set "DB_USER=%VEXXO_APP_DB_USER%"
if not "%VEXXO_APP_DB_HOST%"=="" set "DB_HOST=%VEXXO_APP_DB_HOST%"
if not "%VEXXO_APP_DB_PORT%"=="" set "DB_PORT=%VEXXO_APP_DB_PORT%"

"%ROOT%\enviroment\Scripts\python.exe" manage.py %*
set "EXIT_CODE=%ERRORLEVEL%"

popd >nul
endlocal & exit /b %EXIT_CODE%
