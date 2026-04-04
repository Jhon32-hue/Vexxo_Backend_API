# tasks

## Que hace

`tasks` agrupa piezas relacionadas con ejecucion asincrona, scheduling,
dispatch y workers.

No todo esta igual de maduro, pero el directorio existe como punto natural para
separar trabajo de fondo del request path.

## Estructura Actual

- `celery.py`
- `queues.py`
- `retry_policies.py`
- `dispatchers/`
- `listeners/`
- `scheduled/`
- `workers/`

## Rol En El Sistema

Este bloque expresa una idea importante del backend:

- el request web debe terminar rapido
- el trabajo costoso debe ir a colas, jobs o workers

Eso ya se refleja en varios bounded contexts, aunque no toda la operacion este
centralizada dentro de `tasks`.

## Relacion Con Otros Modulos

- `common`
  contratos y eventos transversales.
- `finance.accounts`
  sync, intelligence y outbox workers.
- `payments`
  callbacks, settlement y futuros workers de integracion.
- `alerts`
  enriquecimiento async y potencial evaluacion desacoplada.
- `reports` y `documents`
  candidatos naturales a jobs por lotes o programados.

## Encaje Con GCP

Este directorio esta muy alineado con:

- Cloud Tasks
- Pub/Sub
- Cloud Scheduler
- Cloud Run workers

Incluso cuando ciertas implementaciones concretas aun no esten desarrolladas.

## Estado Actual

Hoy el bloque tiene estructura util, pero buena parte de sus apps internas aun
estan en scaffold. La ejecucion asincrona real del sistema sigue repartida en
los bounded contexts que ya tienen workers propios o dispatch services.
