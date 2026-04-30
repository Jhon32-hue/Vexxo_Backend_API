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

## Backend comun de ejecucion

La capa comun que ya empieza a ordenar esa dispersion es:

- `tasks.async_backends`
  decide `cloud_tasks | local_worker | sync_inline_for_tests | disabled`
- `tasks.outbox_autopublish`
  concentra el autopublish local after-commit de outboxes
- `manage.py run_worker`
  wrapper unificado para workers locales por `job_type`
- `manage.py publish_outbox`
  wrapper unificado para publicadores de outbox

Eso no reemplaza la logica operativa propia de cada contexto.
La ordena bajo una sola topologia de entrega.

## Convenciones actuales

- `tasks.async_backends` ya gobierna `accounts.sync`, `accounts.intelligence`,
  `alerts.ai`, `transactions.voice` e `identity.consents`
- la politica oficial ya vive en `ASYNC_EXECUTION_MODE*` y
  `ASYNC_EXECUTION_FALLBACK_MODE*`, no en banderas legacy por contexto
- `manage.py publish_outbox` ya propaga `worker_id` de forma homogena a los
  publicadores canonicos, incluyendo `payments`
- `identity.consents` entra por la misma frontera comun, pero hoy no expone un
  `run_worker` durable propio; su modo local oficial es
  `ASYNC_EXECUTION_MODE_IDENTITY_CONSENTS=sync_inline_for_tests`
