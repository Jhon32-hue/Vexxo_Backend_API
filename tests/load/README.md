# Pruebas de carga locales

La suite Artillery mide dos superficies distintas:

- `artillery.public.yml`: health/readiness sin autenticacion.
- `artillery.authenticated.yml`: recorrido mobile read-only por sync-state,
  bootstrap, notificaciones, deudas, metas y pagos programados.

No crea transacciones, pagos, documentos ni otras entidades financieras. Los
reportes se escriben en `.runtime/artillery` y no se versionan.

## Instalacion

```powershell
$env:NODE_OPTIONS = "--use-system-ca"
npm install --prefix tests/load --no-audit --no-fund
```

Se usa el almacen CA del sistema; no se debe desactivar `strict-ssl`.

## Ejecucion

```powershell
.\scripts\run_artillery.ps1 -Profile smoke
.\scripts\run_artillery.ps1 -Profile baseline
.\scripts\run_artillery.ps1 -Profile stress

$env:ARTILLERY_ACCESS_TOKEN = "token-local-efimero"
.\scripts\run_artillery.ps1 -Profile authenticated
.\scripts\run_artillery.ps1 -Profile authenticated-stress
Remove-Item Env:\ARTILLERY_ACCESS_TOKEN
```

Para medir capacidad del servidor y no la concurrencia ilimitada de `runserver`,
levanta el mismo stack local con el override de rendimiento:

```powershell
.\scripts\run_stack.ps1 local up full -Performance -Build
.\scripts\run_stack.ps1 local status full -Performance
```

El perfil usa Gunicorn `gthread` con 2 workers y 4 threads. Eso limita la API a
8 conexiones simultaneas potenciales. Cada worker se recicla despues de 10.000
solicitudes mas un jitter de hasta 1.000, evitando reinicios sincronizados. Los
12 procesos de fondo del slice
`full`, una reserva operativa de 20 y las 8 de API declaran 40 conexiones sobre
97 utilizables de PostgreSQL (`100 - 3` reservadas). `db_connection_budget
--strict` valida la aritmetica al iniciar y consultar estado.

Artillery publica metricas por endpoint. Asi se puede separar la latencia de
`mobile/bootstrap` de la saturacion general. Para inspeccionar SQL repetido sin
registrar tokens ni payloads financieros:

```powershell
docker compose --env-file .env.local -f docker-compose.local.yml `
  -f docker-compose.performance.yml exec -T api `
  python manage.py profile_mobile_queries --email usuario@local.test --endpoint bootstrap
```

`authenticated-stress` sigue siendo una prueba de ruptura deliberada. Un fallo
no debe corregirse subiendo `max_connections` sin revisar primero workers,
threads, consultas por endpoint y procesos de fondo.

## Linea base local

Corrida de referencia del 2026-09-16 con `full -Performance`, 2 workers y 4
threads:

- 2.160 solicitudes, 2.160 respuestas HTTP 200 y cero usuarios virtuales
  fallidos.
- latencia global p95 de 407,5 ms y p99 de 572,6 ms.
- `mobile/bootstrap`: p95 de 561,2 ms y p99 de 620,3 ms.
- `mobile/sync-state`: p95 de 478,3 ms y p99 de 584,2 ms.
- sin errores PostgreSQL ni reciclado de workers durante la corrida.

El perfil SQL inicial sobre un usuario tecnico vacio conto 53 consultas para
bootstrap y 38 para sync-state, pero no permitia negar N+1 dependientes del
volumen. Por eso se agrego `benchmark_mobile_queries`. Los fixtures
transaccionales demostraron y permitieron corregir N+1 en metas y presupuestos
compartidos, ademas de conteos repetidos en outboxes. La linea base posterior es
constante antes del contrato incremental: 74 consultas para bootstrap y 23 para
sync-state. La linea base vigente separa escenarios: 90 consultas para el
primer bootstrap, 18 para bootstrap con cache valida y 23 para sync-state,
siempre con crecimiento cero.

Los resultados Artillery siguientes son anteriores a ese cambio contractual y
deben repetirse antes de atribuirle una variacion de latencia.

La repeticion de Artillery posterior mantuvo 2.160/2.160 HTTP 200, p95 global
de 450,4 ms y p99 de 584,2 ms. `bootstrap` registro p95 de 596 ms y sync-state
459,5 ms. La variacion frente a la corrida anterior no permite atribuir una
mejora de latencia al cambio SQL; la mejora comprobada es menor cantidad de
consultas y crecimiento cero. El reporte esta en
`.runtime/artillery/authenticated-stress-20260916-194055.json`.

El reporte reproducible de esa corrida queda fuera de Git en
`.runtime/artillery/authenticated-stress-20260916-165729.json`.

Estas mediciones sirven para comparar cambios en el mismo equipo local. No
predicen capacidad cloud ni produccion.
