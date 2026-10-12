# Operacion local

## Auditoria documental

`py -3 scripts/audit_backend_docs.py --write` regenera las secciones de evidencia
de los README de dominio y `docs/BACKEND_DOCUMENTATION_AUDIT.md`.
`--check` retorna codigo 1 si detecta deriva. Usa AST, no importa Django ni
lee secretos. Las narrativas y secuencias se revisan en
`docs/BACKEND_CURRENT_FLOW.md`; los diagramas generados expresan imports,
no orden de ejecucion ni una certificacion del comportamiento financiero.

Este directorio contiene el unico entrypoint operativo soportado durante la
etapa local-first. Los scripts no contienen credenciales ni logica de negocio.

## Comando canonico

```powershell
Copy-Item .env.local.example .env.local
.\scripts\run_stack.ps1 local up core -Build
.\scripts\run_stack.ps1 local status core
.\scripts\run_stack.ps1 local verify full
.\scripts\run_stack.ps1 local logs core -Follow
.\scripts\run_stack.ps1 local down
```

El wrapper `run_stack.cmd` acepta los mismos argumentos.

## Perfil local de rendimiento

El rendimiento no es otro entorno ni otro fork de aplicacion. Es un override
del stack `local` que reemplaza `runserver` por Gunicorn y conserva la misma DB,
outboxes, workers y scheduler:

```powershell
.\scripts\run_stack.ps1 local up full -Performance -Build
.\scripts\run_stack.ps1 local status full -Performance
.\scripts\run_stack.ps1 local logs full -Performance -Follow
.\scripts\run_stack.ps1 local down -Performance
```

Los defaults son 2 workers por 4 threads, reciclado en 10.000 solicitudes mas
jitter de hasta 1.000, `CONN_MAX_AGE=0`, 8 conexiones API, 12 para procesos de
fondo y 20 de reserva operativa. El runner ejecuta
`db_connection_budget --strict`; si la suma declarada supera la capacidad util
de PostgreSQL, el arranque falla de forma visible. Los valores se ajustan con
`VEXXO_LOCAL_*` en `.env.local`, no dentro del dominio.

## Coleccion Postman

La coleccion local se mantiene como codigo para que nuevos endpoints no exijan
editar manualmente varios artefactos:

```powershell
py -3 .\scripts\generate_postman_collection.py
```

El comando regenera `postman/Vexxo_local.postman_collection.json` y su guia.
Despues se importa el JSON reemplazando la coleccion `Vexxo_API` en Postman.
No se versionan tokens, passwords ni claves de proveedores; los valores
sensibles deben permanecer vacios y configurarse localmente o en Postman Vault.

## Slices

- `core`: PostgreSQL y API.
- `auth`: core y outbox de identidad.
- `accounts`: core, outbox y workers de cuentas.
- `alerts`: core, outbox y worker de IA para alertas.
- `transactions`: core, outbox y worker de inferencia de voz.
- `payments`: core, outbox de pagos y scheduler local.
- `debts`: core, outbox compartido de deudas/metas y scheduler local.
- `planning`: core, outbox compartido de deudas/metas y scheduler local.
- `documents`: core, ClamAV, worker OCR y outbox documental.
- `full`: todos los procesos locales.

`up` levanta PostgreSQL, ejecuta migraciones y arranca el slice. El equipo no
debe ejecutar manualmente cada worker.

El wrapper `publish_outbox` es propietario del polling continuo. Los comandos
de cada bounded context procesan un lote y no necesitan implementar opciones
operativas comunes para poder ejecutarse en Docker.

`domain-outbox` ejecuta `publish_outbox debts,goals,documents --loop`. Los nuevos
bounded contexts compatibles se agregan al catalogo central
`tasks/outbox_registry.py`, no a ramas de configuracion por entorno.

`scheduler-local` ejecuta `run_scheduler --loop`. Sus jobs viven en
`tasks/scheduled/registry.py`, usan un advisory lock de PostgreSQL y persisten
salud en `task_scheduled_scheduledjobstate`. Agregar un job requiere una entrada
en ese catalogo, no otro contenedor ni cambios por entorno.

`local test` descubre los modulos de prueba automaticamente. Agregar un modulo
nuevo no requiere editar este script para incorporarlo a la suite completa. La
base `test_vexxo` se reutiliza con `--keepdb --noinput`, por lo que la ejecucion
es repetible dentro de Docker y nunca queda esperando confirmacion interactiva.
`local verify` ejecuta en una sola compuerta los checks de Django y migraciones,
runtime, activacion de seguridad, gobierno JSON, filtros API y certificacion de
Open Banking. No sustituye `local test`; esta pensado para validacion rapida del
stack ya levantado.

## Datos locales

```powershell
.\scripts\backup_local_db.ps1
.\scripts\restore_local_db.ps1 -BackupPath .runtime\backups\vexxo-local-YYYYMMDD-HHMMSS.dump -ConfirmRestore
py -3 .\scripts\load_test_local.py --requests 1000 --concurrency 25
docker compose -f docker-compose.local.yml exec -T api python manage.py prune_operational_data
```

## Seguridad

La operacion sensible tambien usa el entrypoint unico:

```powershell
.\scripts\run_stack.cmd local security-status
.\scripts\run_stack.cmd local key-rotation-status
.\scripts\run_stack.cmd local rotate-keys full --limit 25
docker compose --env-file .env.local -f docker-compose.local.yml exec -T api python manage.py open_banking_certification_status --strict
```

`rotate-keys` procesa credenciales por lotes hasta que no queden envelopes con
una version distinta de la activa. No se levanta otro servicio permanente.

El keyring local se genera y respalda sin imprimir llaves. El respaldo usa
DPAPI `CurrentUser`, vive bajo `.runtime/` y solo puede recuperarlo el mismo
usuario de Windows:

```powershell
.\scripts\manage_local_keyring.ps1 -Action Initialize
.\scripts\manage_local_keyring.ps1 -Action Rotate
.\scripts\run_stack.cmd local rotate-keys full --limit 25
.\scripts\manage_local_keyring.ps1 -Action Status
```

`Rotate` conserva las versiones anteriores para lectura. Solo se retira una
version despues de `key_retirement_check` y de verificar el respaldo.
La certificacion Open Banking informa credenciales y vectores oficiales sin
mostrar sus valores. `local_mock` debe estar listo; Belvo/Salt Edge pueden
seguir bloqueados hasta completar su sandbox real.

La suite Artillery reproducible vive en `tests/load/`:

```powershell
$env:NODE_OPTIONS = "--use-system-ca"
npm install --prefix tests/load --no-audit --no-fund
.\scripts\run_artillery.ps1 -Profile smoke
.\scripts\run_artillery.ps1 -Profile baseline
```

Los perfiles autenticados requieren `ARTILLERY_ACCESS_TOKEN`; ningún token se
guarda en archivos. `authenticated-stress` busca el punto de ruptura y puede
fallar intencionalmente. Consulta `tests/load/README.md` para alcance y limites.

El costo SQL del BFF mobile se valida sin persistir fixtures:

```powershell
docker compose --env-file .env.local -f docker-compose.local.yml `
  -f docker-compose.performance.yml exec -T api `
  python manage.py benchmark_mobile_queries --max-query-growth 0
```

El comando aplica presupuestos absolutos de 80 consultas para bootstrap y 25
para sync-state, ademas de exigir crecimiento cero entre small y large.

`prune_operational_data` es dry-run por defecto. Solo elimina outboxes ya
publicados y notificaciones leidas cuando se agrega `--apply`; nunca elimina
ledger, pagos, deudas, metas ni auditoria financiera.

### Reglas de secretos

- `.env.local` nunca se versiona.
- `.env.local.example` solo contiene defaults no sensibles.
- Claves de proveedores externos permanecen fuera del Compose.
- Las CA locales se entregan al build como secretos y `.runtime/` no se versiona.
- Un secreto que aparezca en Git debe rotarse, aunque luego se elimine.

Los antiguos scripts Python vacios fueron eliminados. Un backfill futuro debe
tener objetivo, idempotencia, dry-run y pruebas.
