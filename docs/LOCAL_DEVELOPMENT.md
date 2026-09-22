# Desarrollo local

## Requisitos

- Docker Desktop con contenedores Linux.
- PowerShell.
- Puertos 8000 y 54329 disponibles, o overrides en `.env.local`.

## Primer arranque

```powershell
Copy-Item .env.local.example .env.local
.\scripts\run_stack.ps1 local up core -Build
```

Antes de usar credenciales de proveedores, completa manualmente las variables
de llaves que permanecen vacias en `.env.local.example`. No copies valores a
Compose, settings ni Git. La generacion y rotacion estan descritas en
[`security/README.md`](../security/README.md).

El comando construye la imagen, levanta PostgreSQL, ejecuta migraciones,
arranca Django y valida readiness.

Si un antivirus o proxy inspecciona HTTPS, el runner exporta la CA local de
AVG como secreto temporal de BuildKit. Para otra CA corporativa se puede
definir `VEXXO_LOCAL_CA_CERT_PATH` con la ruta a un certificado PEM. La CA se
usa sin desactivar la validacion TLS y los artefactos automaticos quedan en
`.runtime/`, fuera de Git.

## Desarrollo por flujo

```powershell
.\scripts\run_stack.ps1 local up accounts
.\scripts\run_stack.ps1 local up transactions
.\scripts\run_stack.ps1 local up full
```

No es necesario registrar un modulo por entorno. Solo un job durable nuevo
requiere incorporarse al comando unificado de workers y al slice que lo usa.

## Diagnostico

```powershell
.\scripts\run_stack.ps1 local status full
.\scripts\run_stack.ps1 local logs full -Follow
.\scripts\run_stack.ps1 local check core
.\scripts\run_stack.ps1 local test core
.\scripts\run_stack.ps1 local security-status
.\scripts\run_stack.ps1 local key-rotation-status
```

Sin argumentos adicionales, `test` descubre automaticamente todos los modulos
`tests.py` y `test_*.py`. Las pruebas de una funcionalidad nueva no se registran
manualmente en el runner.

PostgreSQL usa un volumen persistente. `down` no elimina datos.

## PostgreSQL y pgAdmin

No se debe mantener una segunda base PostgreSQL para desarrollo. Docker es el
servidor y pgAdmin es solo el cliente grafico:

- host: `127.0.0.1`
- puerto: `54329` por defecto
- database: `VEXXO_LOCAL_DB_NAME`
- usuario: `VEXXO_LOCAL_DB_USER`
- password: `VEXXO_LOCAL_DB_PASSWORD`

Los contenedores usan el mismo servidor mediante `db:5432`. Refresca
`Schemas > public > Tables` en pgAdmin despues de ejecutar migraciones.
