# observability

## Que hace

`observability` agrupa piezas pensadas para salud operativa, metricas, logs y
tracing del sistema.

## Archivos Presentes

Hoy el directorio contiene:

- `dashboards.py`
- `healthchecks.py`
- `logging.py`
- `metrics.py`
- `tracing.py`

## Estado Del Codigo

En esta pasada no detecte implementacion funcional visible en esos archivos.
Eso sugiere que el directorio esta preparado como frontera de operacion, pero no
todavia materializado como modulo fuerte equivalente a los contextos de negocio.

## Rol En El Sistema

El nombre del bloque sigue siendo importante. Vexxo necesita observabilidad real
para:

- latencia de requests y workers
- lag de outbox y consumidores
- fallos de callback o integracion externa
- tracing de sync, payments y alertas
- soporte operativo y auditoria

## Casos De Uso Naturales

- healthchecks internos
- metricas de lag o throughput
- dashboards de operacion
- correlacion de errores y latencias
- trazas end-to-end entre request, worker y callback

## Relacion Con Otros Modulos

- `common`
  eventos, helpers y contexto transversal.
- `payments`
  intents, callbacks, settlement y operacion por proveedor.
- `finance.accounts`
  outbox, sync, fallback e inteligencia.
- `notifications` y `realtime`
  calidad de entrega y feedback al usuario.
- `support.audit`
  visibilidad funcional complementaria.

## Encaje Con GCP

Este bloque esta pensado para integrarse con:

- Cloud Logging
- Cloud Monitoring
- Cloud Trace
- Error Reporting
- OpenTelemetry si se profundiza tracing distribuido

## Estado Actual

La intencion arquitectonica esta clara, pero la implementacion observable hoy se
encuentra repartida en logs, servicios y contextos especificos, no centralizada
todavia aqui.
