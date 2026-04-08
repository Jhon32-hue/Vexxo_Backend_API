# Auditoria de Eventing y Cloud Readiness

## Principio rector

Cada correccion o mejora sobre arquitectura distribuida en Vexxo debe respetar
este principio:

- lo mas incompleto para cloud hoy es la homogeneidad del eventing y la capa
  real de integraciones separada

Eso significa:

- los bounded contexts deben parecerse entre si en publicacion, retry,
  idempotencia y trazabilidad
- el backend canonico sigue siendo el productor de eventos y la fuente de verdad
- `integrations_stub` no debe absorber dominio; solo actuar como frontera
  temporal hacia un futuro `integration_service`

## Objetivo de esta pasada

Esta pasada no rehace toda la arquitectura. Endurece la base comun donde ya era
posible sin romper contratos existentes:

- settings HTTP mas seguros por entorno
- bus local async menos fragil bajo carga
- outbox operativo mas homogeneo en `alerts`, `payments` e `identity`
- mejor control de duplicados en `transactions` para fuentes externas

## Hecho en esta pasada

### 1. HTTP y seguridad base

Se endurecio [backend/settings.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/backend/settings.py):

- `CORS_ALLOW_ALL_ORIGINS` ya no queda abierto siempre; por defecto solo en local
- `SECURE_SSL_REDIRECT` queda gobernado por entorno
- `SESSION_COOKIE_SECURE` y `CSRF_COOKIE_SECURE` quedan gobernados por entorno
- se agrego base HSTS configurable

### 2. Runtime async local del bus

Se endurecio [common/domain_events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/common/domain_events.py):

- `run_async=True` deja de crear un thread ad-hoc por listener
- ahora usa `ThreadPoolExecutor` con limite configurable por proceso
- los errores async quedan loggeados al resolver el `future`

Esto mejora el runtime local, pero no reemplaza outbox ni convierte el bus local
en cola durable.

### 3. `alerts` entra al patron de outbox

Se agrego outbox propio para `alerts.created.v1`:

- [alerts/alerts/models/outbox.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/alerts/models/outbox.py)
- [alerts/alerts/event_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/alerts/event_service.py)
- [alerts/alerts/management/commands/alerts_publish_outbox.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/alerts/management/commands/alerts_publish_outbox.py)

Y [alerts/alerts/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/alerts/services.py) ya no publica `alerts.created.v1` directo; ahora persiste, encola y publica despues del commit en local o por worker en cloud.

### 4. `payments` mejora su operacion de outbox

Se endurecio el outbox de `payments` en:

- [payments/payment_intents/models.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/payments/payment_intents/models.py)
- [payments/payment_intents/management/commands/payments_publish_outbox.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/payments/payment_intents/management/commands/payments_publish_outbox.py)

Cambios:

- `claim_for_processing()` para evitar doble trabajo concurrente
- recuperacion de eventos `PROCESSING` stale
- respeto de `next_attempt_at`
- backoff exponencial en `mark_failed()`

### 5. `identity` mejora su outbox

Se endurecio `identity.eventing` en:

- [identity/eventing/models.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/models.py)
- [identity/eventing/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/services.py)
- [identity/eventing/management/commands/identity_publish_outbox.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/management/commands/identity_publish_outbox.py)

Cambios:

- `request_id`
- `next_attempt_at`
- `dead_lettered_at`
- `dead_letter_reason`
- `DEAD_LETTER`
- `claim_for_processing()`
- backoff y retry operativo

### 6. Duplicados de transacciones externas

Se endurecio la validacion de `transactions` en
[finance/transactions/transaction_validation_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/transactions/transaction_validation_service.py):

- si la fuente no es manual y llega `provider + external_id`, ya no se acepta
  crear otra transaccion igual en el mismo ledger owner

### 7. Intake canonico para `transactions`

`transactions` ya no depende solo del CRUD manual o de reflejos desde
`payments`.

Ahora existe una capa explicita de intake externo en:

- [finance/transactions/Models/intake.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/transactions/Models/intake.py)
- [finance/transactions/transaction_intake_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/transactions/transaction_intake_service.py)
- [finance/transactions/Views/intake_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/transactions/Views/intake_views.py)

Con:

- `TransactionIntakeBatch`
- `TransactionIntakeReceipt`
- `TransactionSourceLink`
- `TransactionReconciliationIssue`
- endpoints internos para `integration_service`
- decision explicita `duplicate/materialized/updated/noop/corrected/reversed`

### 8. Resolucion formal y write path manual en `transactions`

`transactions` ya no se queda solo en detectar el issue.

Ahora tambien existe:

- `transaction_reconciliation_service.py`
  - resuelve `TransactionReconciliationIssue`
  - soporta `apply_provider_update`, `create_adjustment`,
    `create_reversal` e `ignore`
- endpoint interno
  - `POST /api/internal/transactions/reconciliation/issues/{id}/resolve/`
- `transaction_write_service.py`
  - mueve el create/update/delete manual fuera del camino puro de signals
  - publica eventos de CRUD de forma explicita
  - deja signals como fallback para paths aun no migrados
  - tambien soporta ya varias acciones manuales del dominio sin volver al save
    puro del modelo

## Estado por hallazgo original

### Resuelto o claramente mejorado

- `backend/settings.py`
  - `CORS_ALLOW_ALL_ORIGINS` deja de quedar abierto por defecto en cloud
  - se agregan `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
    `SECURE_SSL_REDIRECT` y HSTS configurables por entorno
- `alerts`
  - `alerts.created.v1` deja de publicarse directo desde el request path
  - entra al patron de outbox con retry, dead-letter y worker propio
- `common.domain_events`
  - `run_async=True` deja de crear un thread ad-hoc por listener
  - ahora usa `ThreadPoolExecutor` acotado y con logging de errores

### Mejorado pero todavia no homogeneo

- `payments`
  - ya tiene `claim_for_processing()`, backoff y `next_attempt_at`
  - aun no iguala a `accounts` en trazabilidad operativa y fases
- `identity`
  - ya tiene dead-letter, `next_attempt_at`, `request_id` y worker con claim
  - aun no iguala a `accounts` en observabilidad rica
- `transactions`
  - mejora la proteccion de duplicados para `provider + external_id`
  - ya tiene intake canonico, source link y endpoints internos
  - ya tiene cierre formal de reconciliation issues y menos dependencia del
    CRUD manual sobre signals
  - sigue faltando reconciliacion mas rica y upsert mas profundo

### Pendiente estructural

- `transactions`
  - el lifecycle ya no depende igual del todo de signals, pero intake,
    materializaciones, participants, scheduled payments y varios paths
    secundarios aun pasan por ahi
- `integrations_stub`
  - sigue siendo frontera temporal
  - no existe aun un `integration_service` real separado consumiendo el bus
- observabilidad transversal
  - el proyecto todavia no tiene paridad plena entre bounded contexts en
    publisher metrics, fases, errores operativos y trazabilidad de punta a
    punta

## Lo que sigue pendiente

### 1. `transactions` todavia no tiene reconciliacion e idempotencia completas

Sigue faltando:

- upsert/reconciliation mas rica para open banking
- fingerprint canonico por proveedor
- correccion/reversion formal para casos extremos adicionales por proveedor,
  especialmente cuando cambian mas dimensiones del payload o aparecen reglas de
  rail mas ricas

### 2. `transactions` sigue muy apoyado en signals

Sigue faltando:

- mover mas lifecycle critico a servicios/casos de uso
- dejar signals como adaptador fino, no como coordinador principal

### 3. El bus async local sigue sin ser transporte durable

Aunque mejoro, sigue faltando:

- backpressure formal
- dead-letter propio
- garantias equivalentes a cola durable

### 4. La observabilidad aun no es perfectamente homogenea

`accounts` sigue siendo el patron mas maduro en publisher, duracion, fases y
backoff. `payments`, `identity` y `alerts` mejoraron, pero aun no igualan ese
nivel de trazabilidad operativa.

### 5. `integrations_stub` sigue siendo stub

Sigue pendiente:

- `integration_service` separado
- consumidores reales de Pub/Sub / Cloud Tasks
- contrato canonico de retorno al backend

## Validacion de esta pasada

Se valido con:

- `manage.py check`
- `compileall` sobre archivos y paquetes tocados
- `makemigrations` de `alerts` e `identity_eventing`
- `makemigrations transactions`
- `manage.py test finance.transactions.tests --keepdb`

No se corrio la suite completa del proyecto en esta pasada.

## Conclusión

Esta pasada mejora la homogeneidad del eventing, pero no la cierra del todo.

Lo mas importante que cambio:

- `alerts` ya entra al patron de outbox
- `payments` e `identity` ya tienen una operacion de outbox menos desigual
- el runtime async local deja de ser tan ingenuo
- la superficie HTTP ya no queda abierta por defecto en cloud

Lo mas importante que sigue faltando:

- ingestion canonica e idempotente en `transactions`
- seguir bajando dependencia de signals en paths no manuales
- separacion real de `integration_service`
- observabilidad operativa totalmente homogenea entre bounded contexts
