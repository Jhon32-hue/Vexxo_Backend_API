# Documentacion

Este archivo centraliza avances funcionales y tecnicos del proyecto. La idea es
ir agregando aqui, por secciones o entradas nuevas, los cambios relevantes del
backend para que equipos tecnicos y no tecnicos tengan una referencia comun.

## Avance: Accounts, Eventos, Realtime, Notificaciones, Sync Interno Y Cloud

### 1. Vision General
`finance.accounts` es el bounded context de cuentas financieras de Vexxo. En
lenguaje tecnico, es el modulo que modela el agregado `Account`, sus permisos
compartidos, sus balances cacheados, su reconciliacion contable y sus eventos
de dominio. En lenguaje simple: es el lugar donde el sistema entiende "donde
vive el dinero", "quien puede usarlo", "cuanto saldo hay", "si ese saldo esta
cuadrado" y "a quien hay que avisarle cuando algo cambia".

El modulo participa en:
- cuentas personales y compartidas
- limites por plan
- integracion con proveedores externos
- jobs de sincronizacion
- reconciliacion entre cache y ledger
- auditoria
- outbox y eventos de dominio
- notificaciones persistentes
- senales realtime para UI

### 2. Mapa De Carpetas Y Responsabilidades

#### 2.1. Modulo `finance.accounts`
- [finance/accounts/models](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/models)
  Que hace: define las entidades persistentes.
- [finance/accounts/serializers](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/serializers)
  Que hace: valida entrada y arma salida HTTP.
- [finance/accounts/views](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/views)
  Que hace: expone CRUD y acciones de dominio.
- [finance/accounts/services](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services)
  Que hace: encapsula reglas operativas, publicaciÃ³n de eventos, reconciliaciÃ³n,
  realtime y orquestaciÃ³n de sync.
- [finance/accounts/domain](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/domain)
  Que hace: define vocabulario, guardas y contratos de eventos.
- [finance/accounts/signals.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/signals.py)
  Que hace: reacciona a cambios de transacciones.
- [finance/accounts/use_cases.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/use_cases.py)
  Que hace: actualiza balance incremental cuando el ledger cambia.
- [finance/accounts/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/event_handlers.py)
  Que hace: escucha eventos de `accounts` y dispara tareas internas o senales
  realtime.

#### 2.2. Modulos Relacionados Ya Conectados
- [finance/transactions](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/transactions)
  Relacion: su ledger alimenta el saldo de las cuentas.
- [alerts/alerts/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/alerts/event_handlers.py)
  Relacion: escucha cambios de balance, drift y fallos de sync.
- [notifications/deliveries](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/deliveries)
  Relacion: guarda el inbox persistente del usuario.
- [notifications/listeners/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/listeners/event_handlers.py)
  Relacion: convierte eventos de dominio en entregas persistentes.
- [realtime/consumers](/c:/Users/Alamb/Documents/Vexxo_Backend_API/realtime/consumers)
  Relacion: guarda senales livianas para polling/UI.
- [integrations_stub/banks](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks)
  Relacion: receptor temporal interno de jobs de sync mientras el
  `integrations_service` no esta separado.
- [support/audit](/c:/Users/Alamb/Documents/Vexxo_Backend_API/support/audit)
  Relacion: registra auditoria de acciones criticas.
- [common/domain_events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/common/domain_events.py)
  Relacion: bus local y catalogo base de eventos.
- [common/gcp/pubsub_dispatcher.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/common/gcp/pubsub_dispatcher.py)
  Relacion: dispatcher opcional a Pub/Sub.

### 3. Modelo De Dominio

#### 3.1. Entidades Principales
- [Account](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/models/account.py)
  Representa una cuenta financiera: banco, efectivo, wallet, credito, broker,
  cripto, ahorro, etc.
- [AccountMembership](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/models/membership.py)
  Sistema moderno de permisos compartidos.
- [BalanceSnapshot](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/models/balance_snapshot.py)
  Foto de reconciliacion entre balance cacheado y balance recomputado.
- [DomainEventOutbox](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/models/outbox.py)
  Cola transaccional de eventos del modulo.
- [NotificationDelivery](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/deliveries/models.py)
  Inbox persistente para usuarios.
- [RealtimeSignal](/c:/Users/Alamb/Documents/Vexxo_Backend_API/realtime/consumers/models.py)
  Feed tecnico liviano para polling/realtime.

#### 3.2. Relaciones
- `Account.owner -> User`
- `Account.memberships -> AccountMembership[]`
- `Account.balance_snapshots -> BalanceSnapshot[]`
- `Transaction.account -> Account`
- `DomainEventOutbox.aggregate_id -> Account.id`
- `NotificationDelivery.owner -> User`
- `RealtimeSignal.owner_id -> User.id` como relacion logica

#### 3.3. Decision Oficial Sobre Sharing Moderno Y Legacy
Esta decision ya queda tomada para el modulo:
- `AccountMembership` es la fuente canonica para permisos compartidos.
- `read_only`, `shared_from_user` y `AccountAccess` se mantienen solo por
  compatibilidad temporal.
- Los flujos nuevos deben usar `AccountMembership`.
- Las banderas legacy no deben crecer ni usarse como segundo sistema moderno.

Eso ya se refleja en:
- [membership.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/models/membership.py)
- [permission_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/permission_service.py)

En lenguaje simple:
- antes habia dos maneras de representar acceso compartido
- ahora Vexxo se queda con una sola como camino oficial
- la vieja sigue viva un tiempo para no romper compatibilidad

### 4. API Publica E Interna

#### 4.1. Punto De Entrada Publico
Montaje principal:
- [api/v1/routers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/api/v1/routers.py)

Base publica:
- `/api/finance/accounts/`

#### 4.2. CRUD Y Acciones De `cuentas`
Recurso:
- `/api/finance/accounts/cuentas/`

Metodos CRUD:
- `GET /cuentas/`
  Lista cuentas visibles para el usuario.
- `POST /cuentas/`
  Crea una cuenta.
- `GET /cuentas/{id}/`
  Devuelve detalle.
- `PUT /cuentas/{id}/`
  Reemplaza el recurso completo.
- `PATCH /cuentas/{id}/`
  Actualiza parcialmente.
- `DELETE /cuentas/{id}/`
  Elimina logicamente o cierra segun reglas del dominio.

Acciones de dominio:
- `POST /cuentas/{id}/set_primary/`
- `POST /cuentas/{id}/recalc_balance/`
- `POST /cuentas/{id}/freeze/`
- `POST /cuentas/{id}/unfreeze/`
- `POST /cuentas/{id}/archive/`
- `POST /cuentas/{id}/unarchive/`
- `POST /cuentas/{id}/close_account/`
- `GET /cuentas/{id}/members/`
- `POST /cuentas/{id}/link_external_source/`
- `POST /cuentas/{id}/unlink_external_source/`
- `POST /cuentas/{id}/schedule_sync/`
- `POST /cuentas/{id}/mark_sync_running/`
- `POST /cuentas/{id}/mark_sync_success/`
- `POST /cuentas/{id}/mark_sync_error/`
- `POST /cuentas/{id}/mark_sync_stale/`
- `GET /cuentas/summary/`
- `GET /cuentas/plan_usage/`
- `GET /cuentas/sync_overview/`
- `GET /cuentas/operational_overview/`
- `GET /cuentas/event_contract/`

Ejemplo simple:
```text
POST /api/finance/accounts/cuentas/
```

Que pasa por dentro:
1. serializer valida nombre, moneda, plan y reglas de negocio
2. se crea `Account`
3. se asegura membership del owner si aplica
4. se registra auditoria
5. se publica `accounts.created.v1`

#### 4.3. CRUD Y Acciones De `membresias-cuenta`
Recurso:
- `/api/finance/accounts/membresias-cuenta/`

Metodos CRUD:
- `GET`
- `POST`
- `GET /{id}/`
- `PUT /{id}/`
- `PATCH /{id}/`
- `DELETE /{id}/`

Acciones:
- `POST /accept_invitation/`
- `POST /revoke/`
- `POST /rotate_invitation/`

#### 4.4. CRUD Y Acciones De `snapshots-balance`
Recurso:
- `/api/finance/accounts/snapshots-balance/`

Metodos:
- `GET`
- `POST`
- `GET /{id}/`

Accion:
- `GET /latest/account=<id>`

#### 4.5. CRUD Operativo De `outbox-cuentas`
Recurso:
- `/api/finance/accounts/outbox-cuentas/`

Metodos:
- `GET`
- `GET /{id}/`

Acciones:
- `POST /publish_now/`
- `POST /retry/`
- `POST /release_lock/`
- `GET /health/`
- `GET /contracts/`

#### 4.6. APIs Relacionadas Fuera Del Modulo
Notificaciones persistentes:
- `/api/notifications/deliveries/entregas-notificacion/`
- detalle, `mark_read`, `mark_all_read`, `stats`
- implementacion en [notifications/deliveries/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/deliveries/views.py#L48)

Realtime persistido:
- `/api/realtime/consumers/senales-realtime/`
- detalle, `latest`, `stats`
- implementacion en [realtime/consumers/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/realtime/consumers/views.py#L41)

Endpoint interno de sync:
- `/internal/integrations/banks/accounts/sync/`
- implementacion en [integrations_stub/banks/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/views.py#L34)

### 5. Guards Del Dominio Y Reglas De Plan
Archivo:
- [finance/accounts/domain/guards.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/domain/guards.py)

QuÃ© cambiÃ³ en el mini sprint de hardening:
- `user.plan` pasa a ser la fuente oficial del plan
- `user.settings.plan` queda como fallback temporal
- una cuenta `FROZEN` ahora cuenta contra el plan
- las cuentas principales siguen contÃ¡ndose solo si estÃ¡n `ACTIVE`
- los errores de lÃ­mites ahora traen forma enriquecida

Ejemplo tecnico:
```python
{
    "is_primary": {
        "message": "Tu plan free permite hasta 1 cuentas principales activas.",
        "limit": 1,
        "current": 1,
        "plan": "free",
    }
}
```

Ejemplo en lenguaje simple:
- si el usuario free ya tiene una cuenta principal activa
- y quiere marcar otra
- el backend no responde solo "error"
- responde tambien cual es el limite, cuanto lleva y que plan detectÃ³

Funciones clave:
- `resolve_account_plan(user)`
- `get_account_plan_limits(user)`
- `get_account_plan_usage(user)`
- `account_creation_limit_errors(user, account_type=...)`
- `primary_account_limit_errors(user, exclude_account_id=...)`
- `get_account_plan_snapshot(user)`

### 6. Eventos Del Dominio
Archivo principal:
- [finance/accounts/domain/events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/domain/events.py)

CatÃ¡logo base:
- [common/domain_events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/common/domain_events.py)

#### 6.1. Eventos Actuales De `accounts`
- `accounts.created.v1`
- `accounts.updated.v1`
- `accounts.closed.v1`
- `accounts.primary.changed.v1`
- `accounts.frozen.v1`
- `accounts.unfrozen.v1`
- `accounts.archived.v1`
- `accounts.unarchived.v1`
- `accounts.recalculated.v1`
- `accounts.balance.updated.v1`
- `accounts.balance.snapshot.created.v1`
- `accounts.balance.drift.detected.v1`
- `accounts.external.linked.v1`
- `accounts.external.unlinked.v1`
- `accounts.sync.scheduled.v1`
- `accounts.sync.status.changed.v1`
- `accounts.sync.started.v1`
- `accounts.sync.succeeded.v1`
- `accounts.sync.failed.v1`
- `accounts.membership.created.v1`
- `accounts.membership.invited.v1`
- `accounts.membership.updated.v1`
- `accounts.membership.accepted.v1`
- `accounts.membership.revoked.v1`

#### 6.2. QuÃ© Mejora Se Hizo En Los Builders
Antes del hardening:
- varios IDs podÃ­an salir como enteros o tipos crudos
- el payload core era algo corto

Ahora:
- todos los IDs del contrato salen serializados como `string`
- `build_account_core_payload()` incluye mas contexto base

Ejemplo tecnico de payload core:
```python
{
    "account_id": "123",
    "owner_id": "45",
    "name": "Broker USD",
    "slug": "45-broker-usd-usd",
    "type": "brokerage",
    "role": "savings",
    "ownership": "personal",
    "visibility": "private",
    "status": "active",
    "currency": "USD",
    "institution": "Binance",
    "country": "CO",
    "provider": "binance",
    "external_id": "acc-ext-1",
    "sync_status": "idle",
    "shared_scope_type": "none",
    "shared_scope_id": "",
}
```

Eso hace que:
- consumidores externos tengan un shape mas estable
- futuros UUID no rompan contratos
- cada evento no tenga que andar metiendo extras basicos por separado

#### 6.3. Builders Importantes
- `build_account_core_payload(account)`
- `build_account_balance_payload(...)`
- `build_account_lifecycle_payload(...)`
- `build_account_sync_payload(...)`
- `build_account_membership_payload(...)`
- `build_account_snapshot_payload(...)`

### 7. QuÃ© Escucha QuÃ©

#### 7.1. Listeners Internos De `accounts`
Archivo:
- [finance/accounts/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/event_handlers.py)

Escucha:
- `accounts.sync.scheduled.v1`
  AcciÃ³n: intenta crear Cloud Task
- `accounts.balance.drift.detected.v1`
  AcciÃ³n: log operativo
- `accounts.primary.changed.v1`
  AcciÃ³n: crea seÃ±al realtime
- `accounts.archived.v1`
  AcciÃ³n: crea seÃ±al realtime
- `accounts.sync.succeeded.v1`
  AcciÃ³n: crea seÃ±al realtime

#### 7.2. Listeners De Alertas
Archivo:
- [alerts/alerts/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/alerts/event_handlers.py)

Escucha:
- `accounts.balance.updated.v1`
- `accounts.sync.failed.v1`
- `accounts.balance.drift.detected.v1`

#### 7.3. Listeners De Notificaciones Persistentes
Archivo:
- [notifications/listeners/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/listeners/event_handlers.py)

Escucha:
- `accounts.membership.invited.v1`
- `accounts.membership.accepted.v1`
- `accounts.membership.revoked.v1`
- `accounts.primary.changed.v1`
- `accounts.archived.v1`
- `accounts.sync.succeeded.v1`

### 8. Outbox, Bus Local Y Transporte
Archivos:
- [finance/accounts/services/outbox_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/outbox_service.py)
- [finance/accounts/services/event_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/event_service.py)
- [finance/accounts/models/outbox.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/models/outbox.py)

QuÃ© hace el outbox:
- guarda primero el evento en base de datos
- solo publica despuÃ©s del commit
- evita perder eventos si la transacciÃ³n falla

QuÃ© mejoramos:
- la `idempotency_key` ya no usa SHA-1 sino SHA-256
- se centralizÃ³ metadata estÃ¡ndar del contexto `accounts`
- `transaction_id` se volviÃ³ `str | int | None` para prepararse a UUID

Ejemplo de flujo:
1. una vista o servicio llama `publish_account_event(...)`
2. `outbox_service.py` genera payload y llave estable
3. `event_service.py` crea el registro en `DomainEventOutbox`
4. `transaction.on_commit` llama `publish_outbox_event(...)`
5. el bus local ejecuta listeners
6. si estÃ¡ activado, tambiÃ©n puede despachar a Pub/Sub

### 9. Reconciliacion Y Snapshots
Archivo:
- [finance/accounts/services/reconcile_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/reconcile_service.py)

QuÃ© hace:
- bloquea la cuenta con `select_for_update()`
- compara balance cacheado vs balance recomputado
- crea un `BalanceSnapshot`
- publica eventos de snapshot
- detecta drift material
- opcionalmente repara el balance

#### 9.1. Cambio Clave Del Hardening
Antes:
- `snapshot.is_consistent` usaba el threshold del modelo
- el auto-repair usaba `drift_threshold` del servicio
- eso podÃ­a generar desalineaciÃ³n semÃ¡ntica

Ahora:
- `BalanceSnapshot.is_consistent` sigue significando consistencia fina del modelo
- `drift_threshold` se usa para decidir si el drift es material a nivel
  operativo
- el evento `accounts.balance.drift.detected.v1` se emite cuando el drift es
  material
- `auto_repair` tambiÃ©n depende de drift material

En lenguaje simple:
- una diferencia muy pequeÃ±a puede marcar que los nÃºmeros no son idÃ©nticos
- pero no toda diferencia amerita alerta o reparaciÃ³n
- el servicio ahora diferencia "no es exacto" de "es lo bastante grande como
  para actuar"

#### 9.2. Cambio En `note`
Antes:
- `note="auto_repair"` significaba solo que estaba activado

Ahora:
- `auto_repair_requested` si se pidiÃ³
- `auto_repaired` si realmente se reparÃ³

#### 9.3. Evento De Recalculo Tras Auto Repair
Ahora, si hay auto-repair material:
- se publica `accounts.balance.updated.v1`
- se publica `accounts.recalculated.v1`

Eso alinea el servicio con el comportamiento que antes solo vivÃ­a en la API.

#### 9.4. Signals, Balance Incremental Y Precision Operativa
Archivos:
- [finance/accounts/signals.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/signals.py)
- [finance/accounts/use_cases.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/use_cases.py)

QuÃ© hacen:
- `signals.py` escucha cambios de `Transaction`
- `use_cases.py` intenta aplicar el cambio como delta incremental
- si el delta no es confiable, `signals.py` hace fallback a `recalc_balance()`

Ejemplo simple:
- una transacciÃ³n cambia de la cuenta A a la cuenta B
- el sistema intenta restar el efecto en A y sumarlo en B sin recalcular todo
- si no puede confiar en ese delta, recalcula por ledger y aun asÃ­ publica
  `accounts.balance.updated.v1`

QuÃ© endurecimos:
- `TransactionBalanceState.tx_id` ya acepta `str | int | None`
- el fallback deja mejor telemetrÃ­a en logs con:
  `reason`, `tx_id`, `affected_account_ids`
- `use_cases.py` deja explÃ­cito que `read_only` sigue participando solo como
  compatibilidad legacy temporal

#### 9.5. Politica Actual De Precision Monetaria
Estado actual del dominio persistido:
- `Account.balance` usa 2 decimales
- `Account.initial_balance` usa 2 decimales
- `Account.last_transaction_amount` usa 2 decimales
- `Transaction.amount` usa 2 decimales
- `BalanceSnapshot` guarda 6 decimales para observaciÃ³n y drift

DecisiÃ³n aplicada:
- el flujo incremental de `use_cases.py` ahora opera con precisiÃ³n `0.01`
  porque esa es la precisiÃ³n real de los modelos persistidos hoy

Por quÃ© se hizo asÃ­:
- antes el incremental operaba a 6 decimales
- pero cuenta y transacciÃ³n se guardaban a 2
- eso podÃ­a crear drift artificial o falsa sensaciÃ³n de precisiÃ³n

QuÃ© significa para negocio:
- hoy el sistema estÃ¡ alineado con dinero fiat tradicional de 2 decimales
- si Vexxo migra a cripto o inversiÃ³n fraccionada con mÃ¡s precisiÃ³n,
  `Account`, `Transaction`, snapshots y use cases deben migrar juntos
- no basta con cambiar un solo archivo

### 10. Realtime
Archivos:
- [finance/accounts/services/realtime_services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/realtime_services.py)
- [realtime/consumers/models.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/realtime/consumers/models.py)
- [realtime/consumers/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/realtime/consumers/views.py#L41)

QuÃ© es:
- una capa liviana para UI, polling o futuros sockets

QuÃ© no es:
- no reemplaza al outbox
- no reemplaza a las alertas
- no reemplaza al inbox persistente

Ejemplo:
- si una cuenta pasa a principal
- ademÃ¡s del evento de dominio
- el sistema genera una `RealtimeSignal`
- la UI puede consultar `/api/realtime/consumers/senales-realtime/`

### 11. Notificaciones Persistentes
Archivos:
- [notifications/deliveries/models.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/deliveries/models.py)
- [notifications/deliveries/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/deliveries/services.py)
- [notifications/deliveries/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/deliveries/views.py#L48)
- [notifications/listeners/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/listeners/event_handlers.py)

QuÃ© es:
- un inbox real del usuario dentro del backend

QuÃ© mejorÃ³:
- ya no son solo intents por log
- ahora se persisten filas reales
- hay API para listarlas y marcarlas como leÃ­das
- la deduplicaciÃ³n ya toma al usuario objetivo real, no solo `payload.user_id`

### 12. Sync Externo E Integrations Stub
Archivos:
- [finance/accounts/services/sync_dispatch_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/sync_dispatch_service.py)
- [integrations_stub/banks/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/views.py#L34)
- [integrations_stub/banks/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/services.py#L25)

Flujo:
1. cuenta agenda sync
2. se publica `accounts.sync.scheduled.v1`
3. listener interno intenta crear Cloud Task
4. Cloud Task llama `/internal/integrations/banks/accounts/sync/`
5. el stub procesa la cuenta
6. publica eventos `started`, `status_changed`, `succeeded` o `failed`

QuÃ© mejorÃ³:
- el receptor interno ya acepta el `event` original dentro del body
- preserva `correlation_id` y `causation_id`
- eso mejora trazabilidad entre el evento agendado y el job realmente ejecutado

### 13. Variables GCP Que Hay Que Rellenar
Archivo:
- [.env](/c:/Users/Alamb/Documents/Vexxo_Backend_API/.env)

#### 13.1. Base GCP
- `GCP_PROJECT_ID`
  Valor esperado: el ID real del proyecto en Google Cloud

#### 13.2. Pub/Sub
- `DOMAIN_EVENTS_PUBSUB_ENABLED`
- `DOMAIN_EVENTS_PUBSUB_TOPIC`
- `DOMAIN_EVENTS_PUBSUB_ENABLE_ORDERING`
- `DOMAIN_EVENTS_PUBSUB_WAIT_FOR_RESULT`
- `DOMAIN_EVENTS_PUBSUB_TIMEOUT_SECONDS`

#### 13.3. Cloud Tasks Para Sync
- `ACCOUNTS_SYNC_CLOUD_TASKS_ENABLED`
- `ACCOUNTS_SYNC_CLOUD_TASKS_QUEUE`
- `ACCOUNTS_SYNC_CLOUD_TASKS_LOCATION`
- `ACCOUNTS_SYNC_HANDLER_URL`
- `ACCOUNTS_SYNC_INTERNAL_TOKEN`
- `ACCOUNTS_SYNC_TASK_SERVICE_ACCOUNT_EMAIL`
- `ACCOUNTS_SYNC_TASK_AUDIENCE`
- `ACCOUNTS_SYNC_TASK_DEADLINE_SECONDS`
- `ACCOUNTS_SYNC_TASK_BUFFER_SECONDS`

#### 13.4. Cloud Tasks Para Inteligencia De Accounts
- `ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_ENABLED`
- `ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_QUEUE`
- `ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_LOCATION`
- `ACCOUNTS_INTELLIGENCE_HANDLER_URL`
- `ACCOUNTS_INTELLIGENCE_INTERNAL_TOKEN`
- `ACCOUNTS_INTELLIGENCE_TASK_SERVICE_ACCOUNT_EMAIL`
- `ACCOUNTS_INTELLIGENCE_TASK_AUDIENCE`
- `ACCOUNTS_INTELLIGENCE_TASK_DEADLINE_SECONDS`
- `ACCOUNTS_INTELLIGENCE_TASK_BUFFER_SECONDS`
- `ACCOUNTS_INTELLIGENCE_LOCAL_FALLBACK_ENABLED`

#### 13.5. Politica De Snapshots
- `ACCOUNTS_BALANCE_SNAPSHOT_SCHEDULED_FREQUENCY`
- `ACCOUNTS_BALANCE_SNAPSHOT_RETENTION_DAYS`
- `ACCOUNTS_BALANCE_SNAPSHOT_INCONSISTENT_RETENTION_DAYS`
- `ACCOUNTS_BALANCE_SNAPSHOT_ON_DEMAND_RETENTION_DAYS`
- `ACCOUNTS_BALANCE_SNAPSHOT_AUTO_REPAIR_RETENTION_DAYS`
- `ACCOUNTS_BALANCE_SNAPSHOT_MAX_PER_ACCOUNT`

#### 13.6. Credenciales
ProducciÃ³n:
- preferir Workload Identity o service account adjunta al servicio

Desarrollo local:
- opcional `GOOGLE_APPLICATION_CREDENTIALS=/ruta/al/service-account.json`

Que rellenar si o si para cloud real:
- `GCP_PROJECT_ID`
- `DOMAIN_EVENTS_PUBSUB_TOPIC` si activaras Pub/Sub
- `ACCOUNTS_SYNC_HANDLER_URL` si activaras Cloud Tasks
- `ACCOUNTS_SYNC_TASK_SERVICE_ACCOUNT_EMAIL` si usaras OIDC
- `ACCOUNTS_SYNC_INTERNAL_TOKEN` si protegeras el endpoint interno con token
- `ACCOUNTS_INTELLIGENCE_HANDLER_URL` si activaras Cloud Tasks para proyecciones
- `ACCOUNTS_INTELLIGENCE_TASK_SERVICE_ACCOUNT_EMAIL` si usaras OIDC para inteligencia
- `ACCOUNTS_INTELLIGENCE_INTERNAL_TOKEN` si protegeras el endpoint interno de inteligencia

### 14. Validaciones Y Pruebas
Archivo:
- [finance/accounts/tests.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/tests.py)

QuÃ© cubre hoy:
- snapshot de plan
- lÃ­mites de cuenta principal
- payloads de eventos
- runtime del pipeline de eventos
- helpers del agregado
- gobierno del catalogo de eventos
- politica operativa de snapshots
- proyecciones basicas de inteligencia de accounts

QuÃ© se endureciÃ³ en el mini sprint:
- tests de IDs serializados como string
- tests de conteo de cuentas `FROZEN` contra el plan
- tests del shape enriquecido de errores

### 15. Estado Actual Del Modulo
Lo mejor resuelto hoy:
- outbox transaccional
- capa de inteligencia derivada por usuario
- proyecciones async listas para Cloud Tasks
- politica de retention y cleanup para snapshots
- gobierno formal del catalogo de eventos
- contrato de eventos centralizado
- reconciliaciÃ³n seria con snapshots
- integraciÃ³n con notificaciones y realtime
- endpoint interno para sync desacoplado de la API pÃºblica

Lo mÃ¡s delicado todavÃ­a:
- coexistencia temporal de sharing moderno y legacy
- falta validar runtime completo con Django/venv real
- falta aplicar migraciones nuevas en todas las bases
- falta decidir cuÃ¡ndo retirar definitivamente `AccountAccess`

### 16. Resumen Ejecutivo
Hoy Vexxo tiene un modulo `accounts` mucho mÃ¡s maduro:
- los eventos salen con contratos mÃ¡s estables
- los lÃ­mites de plan estÃ¡n mÃ¡s claros y mÃ¡s Ãºtiles para frontend
- la reconciliaciÃ³n ya distingue inconsistencia fina de drift material
- los auto-repair ya emiten eventos completos
- el sistema moderno de permisos compartidos quedÃ³ oficialmente definido
- realtime, notificaciones y sync interno ya forman parte del circuito real del mÃ³dulo

En tÃ©rminos simples:
- el backend ya no solo guarda cuentas
- ahora tambiÃ©n entiende estado, lÃ­mites, colaboraciÃ³n, salud operativa y comunicaciÃ³n con el resto del sistema

### 17. Proyecciones Async, Politica De Snapshots Y Gobierno De Eventos

#### 17.1. Proyecciones Async De Inteligencia
Archivos:
- [finance/accounts/services/intelligence_dispatch_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/intelligence_dispatch_service.py)
- [finance/accounts/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/event_handlers.py)
- [integrations_stub/banks/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/views.py)
- [integrations_stub/banks/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/services.py)
- [integrations_stub/banks/urls.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/urls.py)

Que cambio:
- la inteligencia de `accounts` ya no depende solo del listener local en memoria
- ahora existe un dispatcher opcional hacia Cloud Tasks para recalcular snapshots y senales fuera del proceso web
- si Cloud Tasks no esta configurado, el sistema puede hacer fallback local controlado

Variables nuevas en `.env` y `backend/settings.py`:
- `ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_ENABLED`
- `ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_QUEUE`
- `ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_LOCATION`
- `ACCOUNTS_INTELLIGENCE_HANDLER_URL`
- `ACCOUNTS_INTELLIGENCE_INTERNAL_TOKEN`
- `ACCOUNTS_INTELLIGENCE_TASK_SERVICE_ACCOUNT_EMAIL`
- `ACCOUNTS_INTELLIGENCE_TASK_AUDIENCE`
- `ACCOUNTS_INTELLIGENCE_TASK_DEADLINE_SECONDS`
- `ACCOUNTS_INTELLIGENCE_TASK_BUFFER_SECONDS`
- `ACCOUNTS_INTELLIGENCE_LOCAL_FALLBACK_ENABLED`

Endpoint interno nuevo:
- `POST /internal/integrations/banks/accounts/intelligence/refresh/`

Flujo real:
1. ocurre un evento `accounts.*`
2. listener `accounts.refresh_owner_account_intelligence` intenta crear una Cloud Task
3. la task llama el endpoint interno de refresh
4. el stub ejecuta `refresh_account_intelligence_for_user(owner_id)`
5. se actualizan snapshots, risk y product signals
6. si Cloud Tasks no esta activa y el fallback local esta habilitado, el recalculo corre en proceso

Que hay que rellenar en GCP para activarlo:
- `GCP_PROJECT_ID`
- `ACCOUNTS_INTELLIGENCE_HANDLER_URL`
- `ACCOUNTS_INTELLIGENCE_TASK_SERVICE_ACCOUNT_EMAIL` si usas OIDC
- `ACCOUNTS_INTELLIGENCE_INTERNAL_TOKEN` si proteges el endpoint por token
- opcionalmente `GOOGLE_APPLICATION_CREDENTIALS` en local

#### 17.2. Politica Operativa De BalanceSnapshot
Archivos:
- [finance/accounts/services/snapshot_policy_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/snapshot_policy_service.py)
- [finance/accounts/views/snapshot_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/views/snapshot_views.py)
- [finance/accounts/management/commands/accounts_cleanup_balance_snapshots.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/management/commands/accounts_cleanup_balance_snapshots.py)
- [finance/accounts/management/commands/accounts_reconcile_balances.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/management/commands/accounts_reconcile_balances.py)

Variables nuevas:
- `ACCOUNTS_BALANCE_SNAPSHOT_SCHEDULED_FREQUENCY`
- `ACCOUNTS_BALANCE_SNAPSHOT_RETENTION_DAYS`
- `ACCOUNTS_BALANCE_SNAPSHOT_INCONSISTENT_RETENTION_DAYS`
- `ACCOUNTS_BALANCE_SNAPSHOT_ON_DEMAND_RETENTION_DAYS`
- `ACCOUNTS_BALANCE_SNAPSHOT_AUTO_REPAIR_RETENTION_DAYS`
- `ACCOUNTS_BALANCE_SNAPSHOT_MAX_PER_ACCOUNT`

Politica actual:
- snapshots programados: `nightly` por defecto
- snapshots inconsistentes: retencion mas larga
- snapshots on-demand/manuales: retencion intermedia
- snapshots con `auto_repaired`: retencion larga para soporte
- siempre se conserva al menos el snapshot mas reciente por cuenta
- ademas se limita el crecimiento por cuenta con `max_per_account`

API nueva:
- `GET /api/finance/accounts/snapshots-balance/policy/`
  devuelve la politica activa del modulo

Comando nuevo:
- `python manage.py accounts_cleanup_balance_snapshots --dry-run`
- `python manage.py accounts_cleanup_balance_snapshots --show-policy`

Mejora adicional:
- el comando `accounts_reconcile_balances` ahora acepta `--source`
- tambien corrige el filtro de cuentas activas/inactivas usando `status`, no un campo inexistente

#### 17.3. Gobierno Formal Del Catalogo De Eventos
Archivos:
- [finance/accounts/domain/events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/domain/events.py)
- [finance/accounts/views/account_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/views/account_views.py)
- [finance/accounts/views/outbox_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/views/outbox_views.py)
- [finance/accounts/domain/__init__.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/domain/__init__.py)

Que se agrego:
- `get_account_event_governance()`
- metadata formal por evento en el catalogo:
  - `contract_status`
  - `schema_version`
  - `deprecated`
  - `deprecated_by`
  - `visibility`
  - `payload_fields`
  - `required_fields`

Politica actual:
- breaking change => nuevo evento `v2`
- cambio no breaking => solo agregar campos opcionales
- deprecacion antes de remocion
- registry actual = `lightweight_inline_registry`

Donde se consulta:
- `GET /api/finance/accounts/cuentas/event_contract/`
- `GET /api/finance/accounts/outbox-cuentas/contracts/`

En lenguaje simple:
- el catalogo de eventos ya no solo dice "que eventos existen"
- ahora tambien dice "en que version van", "cuales campos trae cada uno" y "si estan activos o deprecados"

## Avance: Identity, Lifecycle De Usuario, OAuth Y Relacion Con Accounts

### 18.1. Vision General
`identity.users` ya no funciona solo como autenticacion. Ahora es el bounded
context que origina el lifecycle del usuario en Vexxo.

En lenguaje tecnico:
- define identidad, estado, plan, onboarding y preferencias base
- publica eventos de dominio al cambiar plan, moneda, estado o onboarding
- deja operativo OAuth2 para Google y Facebook con handoff seguro
- coordina el bootstrap del usuario sin crear directamente recursos de
  `accounts`

En lenguaje simple:
- aqui nace el usuario
- aqui se sabe en que plan esta
- aqui se sabe cual es su moneda base
- desde aqui se dispara la construccion de su espacio financiero

### 18.2. Archivos Nuevos O Ajustados
- [identity/users/models/user.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/models/user.py)
  Se alineo con la matriz canonica de planes y se corrigieron helpers como
  `full_name()` e `is_premium`.
- [identity/users/domain/plan_matrix.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/domain/plan_matrix.py)
  Nueva matriz oficial de capacidades por plan.
- [identity/users/domain/events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/domain/events.py)
  Nuevo contrato de eventos del contexto.
- [identity/users/services/event_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/event_service.py)
  Publica eventos `users.*` despues de commit.
- [identity/users/services/bootstrap_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/bootstrap_service.py)
  Crea categorias, equipo personal y alertas de bienvenida.
- [identity/users/services/oauth_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/oauth_service.py)
  Prepara proveedores Google/Facebook.
- [identity/users/signals.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/signals.py)
  Ya no bootstrappea todo directamente; ahora detecta cambios y emite eventos.
- [identity/users/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/event_handlers.py)
  Reacciona a `users.registered.v1` y `users.onboarding.completed.v1`.
- [finance/accounts/services/user_integration_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/user_integration_service.py)
  Nueva capa de integracion entre lifecycle de usuario y cuentas.
- [finance/accounts/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/event_handlers.py)
  Ahora tambien escucha eventos de `users`.
- [identity/documentacion.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/documentacion.md)
  Documento tecnico detallado del contexto de identidad.

### 18.3. Registro Nuevo
Endpoint:
- `POST /api/identity/users/auth/register/`

Contrato nuevo:
- `full_name`
- `email`
- `password`
- `password2`
- opcionalmente `preferred_currency`, `timezone_name`, `locale`, `phone_number`

Que cambio:
- el frontend ya no necesita mandar `username`
- el backend lo genera automaticamente
- `full_name` se separa en `first_name` y `last_name`
- el usuario nace con `plan=free`

### 18.4. Login, Perfil, Onboarding Y OAuth
Endpoints:
- `POST /api/identity/users/auth/login/`
- `GET|PUT|PATCH /api/identity/users/me/`
- `POST /api/identity/users/onboarding/complete/`
- `GET /api/identity/users/auth/social/providers/`
- `GET /api/identity/users/auth/social/google/start/`
- `GET /api/identity/users/auth/social/facebook/start/`
- `GET /api/identity/users/event-contract/`

OAuth actual:
- valida callback real y resuelve linking o login social
- devuelve `handoff_code` en el callback GET
- crea sesion y JWT solo via `POST /auth/social/exchange/`

### 18.5. Eventos De Usuario
Eventos creados:
- `users.registered.v1`
- `users.profile.updated.v1`
- `users.plan.changed.v1`
- `users.currency.changed.v1`
- `users.onboarding.completed.v1`
- `users.verified.v1`
- `users.suspended.v1`
- `users.activated.v1`
- `users.social_auth.prepared.v1`

Flujo actual:
1. cambia `User`
2. `identity/users/signals.py` detecta el cambio
3. se publica evento al bus local despues del commit
4. listeners de identidad y de `accounts` reaccionan
5. si Pub/Sub esta activo, el dispatcher global tambien lo puede sacar a GCP

### 18.6. Integracion Con Accounts
Cambios clave:
- `users.registered.v1` -> `accounts` crea la cuenta principal del usuario
- `users.plan.changed.v1` -> `accounts` refresca proyecciones
- `users.currency.changed.v1` -> `accounts` alinea `base_currency` en cuentas elegibles
- `users.suspended.v1` -> `accounts` desactiva auto-sync en cuentas externas
- `users.activated.v1` -> `accounts` refresca inteligencia

Esto resuelve la desalineacion anterior donde `identity` creaba cuentas a mano
sin pasar por el dominio moderno de `accounts`.

### 18.7. Matriz Canonica De Planes
Decision tomada:
- `User.plan` es la fuente oficial
- la matriz vive en `identity/users/domain/plan_matrix.py`
- `finance.accounts.domain.guards` ahora usa esa misma base

Resultado:
- `users` y `accounts` ya no pueden decidir limites distintos para el mismo
  usuario

### 18.8. Dashboard De Usuario
Archivo:
- [identity/users/views/dashboard.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views/dashboard.py)

Mejora:
- ya no depende del viejo filtro `is_active=True` sobre `Account`
- usa snapshots y metricas derivadas de `accounts` cuando existen
- si faltan, intenta primero refresco asincrono; solo hace fallback local si el entorno lo permite

### 18.9. Configuracion Cloud Y Credenciales
Variables nuevas en [.env](/c:/Users/Alamb/Documents/Vexxo_Backend_API/.env):
- `GCP_IDENTITY_PLATFORM_ENABLED`
- `GCP_IDENTITY_PLATFORM_PROJECT_ID`
- `GCP_IDENTITY_PLATFORM_TENANT_ID`
- `GCP_IDENTITY_PLATFORM_API_KEY`
- `GOOGLE_OAUTH_ENABLED`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_CALLBACK_URL`
- `FACEBOOK_OAUTH_ENABLED`
- `FACEBOOK_OAUTH_CLIENT_ID`
- `FACEBOOK_OAUTH_CLIENT_SECRET`
- `FACEBOOK_OAUTH_CALLBACK_URL`

Que debes rellenar cuando vayas a activarlo:
- client id / secret y callback de Google
- client id / secret y callback de Facebook
- si usaras Identity Platform, los datos de proyecto / tenant / api key

### 18.10. Documento Tecnico Dedicado
Se creo:
- [identity/documentacion.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/documentacion.md)

Ese archivo explica con mas detalle:
- modelo `User`
- planes
- eventos
- OAuth social
- onboarding
- relacion con `accounts`
- variables GCP

### 18.11. Extensiones De Identidad: Devices, Sessions, Consents, Permissions
Se activaron cuatro submodulos operativos de identidad:
- [identity/devices](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/devices)
- [identity/sessions](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions)
- [identity/consents](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents)
- [identity/permissions](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions)

Que aportan:
- `devices`: huella del cliente, confianza y metadata tecnica
- `sessions`: trazabilidad de acceso, revocacion y correlacion con JWT/device
- `consents`: consentimiento legal y regulatorio, incluyendo open banking
- `permissions`: grants de producto/feature access mas ricos que los permisos
  nativos de Django

Nuevos endpoints:
- `/api/identity/devices/dispositivos/`
- `/api/identity/sessions/sesiones/`
- `/api/identity/consents/consentimientos/`
- `/api/identity/permissions/grants/`

Eventos agregados al contexto identity:
- `users.device.registered.v1`
- `users.device.trusted.v1`
- `users.device.revoked.v1`
- `users.session.started.v1`
- `users.session.revoked.v1`
- `users.consent.granted.v1`
- `users.consent.revoked.v1`
- `users.permission.granted.v1`
- `users.permission.denied.v1`
- `users.permission.revoked.v1`

Uso esperado:
- seguridad y soporte: sesiones/dispositivos
- open banking y data integrations: consentimientos
- enterprise y feature flags: grants de permisos

Evolucion reciente:
- estos submodulos ya se reorganizaron en paquetes internos de `models`,
  `serializers` y `views`
- `sessions` revoca acceso automaticamente cuando un usuario se suspende o un
  dispositivo se revoca
- `consents` ya impacta `finance.accounts`: revocar open banking desactiva
  auto-sync de cuentas externas del proveedor afectado
- `permissions` ya sincroniza grants derivados por plan y por consentimiento

Nuevas acciones de observabilidad:
- `/api/identity/devices/dispositivos/summary/`
- `/api/identity/sessions/sesiones/revoke_all/`
- `/api/identity/sessions/sesiones/summary/`
- `/api/identity/consents/consentimientos/expiring/`
- `/api/identity/consents/consentimientos/summary/`
- `/api/identity/permissions/grants/mine/`
- `/api/identity/permissions/grants/summary/`
- `/api/identity/permissions/grants/effective/`

Mas detalle:
- [identity/documentacion.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/documentacion.md)

### 18.12. Hardening De Identity Y Seguridad Operativa
Archivos nuevos o reforzados:
- [identity/eventing/models.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/models.py)
- [identity/eventing/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/services.py)
- [identity/social_identities/models.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/social_identities/models.py)
- [identity/users/services/oauth_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/oauth_service.py)
- [identity/users/views/auth.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views/auth.py)
- [identity/sessions/models/session.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/models/session.py)
- [identity/sessions/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/services.py)
- [integrations_stub/banks/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/views.py)
- [integrations_stub/banks/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/services.py)
- [.github/workflows/backend-validation.yml](/c:/Users/Alamb/Documents/Vexxo_Backend_API/.github/workflows/backend-validation.yml)

Que se cerro:
- `identity` ya no publica solo con `transaction.on_commit`; ahora persiste en
  `IdentityDomainEventOutbox` y luego publica al bus
- OAuth social ya no esta solo "preparado": ahora existe callback real,
  `state` firmado, exchange de `code`, lectura de perfil remoto y linking
  seguro con `UserSocialIdentity`
- las sesiones ahora manejan `family_id`, rotacion de refresh, deteccion basica
  de reuse, `risk_level` y `requires_step_up`
- revocar consentimiento de open banking ya no solo baja `allow_auto_sync`;
  ahora tambien ejecuta teardown tecnico hacia el stub de integraciones
- `permissions` ya diferencia `grant_kind` entre grants manuales y
  entitlements derivados

Nuevos endpoints publicos:
- `POST /api/identity/users/auth/refresh/`
- `GET /api/identity/users/auth/social/{provider}/callback/`
- `POST /api/identity/users/auth/social/exchange/`
- `GET /api/identity/users/auth/social/identities/`
- `DELETE /api/identity/users/auth/social/{provider}/unlink/`
- `POST /api/identity/sessions/sesiones/revoke_others/`
- `POST /api/identity/sessions/sesiones/revoke_family/`

Nuevo endpoint interno:
- `POST /internal/integrations/banks/consents/revoke/`

Variables nuevas en `.env`:
- `IDENTITY_SOCIAL_STATE_SALT`
- `IDENTITY_SOCIAL_STATE_MAX_AGE_SECONDS`
- `IDENTITY_SOCIAL_AUTO_LINK_BY_EMAIL`
- `IDENTITY_MAX_ACTIVE_SESSIONS`
- `IDENTITY_STEP_UP_ON_UNKNOWN_DEVICE`
- `IDENTITY_STEP_UP_ON_SUSPICIOUS_DEVICE`
- `IDENTITY_STEP_UP_REQUIRED_PATHS`
- `IDENTITY_PROJECTIONS_LOCAL_FALLBACK_ENABLED`
- `IDENTITY_CONSENT_TEARDOWN_HANDLER_URL`
- `IDENTITY_CONSENTS_INTERNAL_TOKEN`
- `IDENTITY_CONSENT_LOCAL_FALLBACK_ENABLED`

Validacion operativa agregada:
- workflow CI en GitHub Actions para `compileall` y `manage.py check`
- migraciones nuevas:
  - [identity/eventing/migrations/0001_initial.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/migrations/0001_initial.py)
  - [identity/social_identities/migrations/0001_initial.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/social_identities/migrations/0001_initial.py)
  - [identity/sessions/migrations/0002_session_security_hardening.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/migrations/0002_session_security_hardening.py)
  - [identity/permissions/migrations/0002_permission_grant_kind.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/migrations/0002_permission_grant_kind.py)

### 18.13. Correcciones Criticas De Coherencia Entre Identity, Accounts E Integrations

Se cerraron estos puntos:
- `identity` ya no tiene un wrapper roto hacia su outbox
- el outbox de `identity` ahora persiste `priority`, `correlation_id` y `causation_id`
- OAuth social ya no emite tokens ni crea sesion sobre `GET callback`
- los permisos derivados y los overrides manuales ya pueden coexistir sin pisarse
- las proyecciones de `accounts` e `identity` ya no deben recomputarse en request path en produccion
- el teardown de consentimientos ya usa secreto propio y una capa de dispatch
- el `SocialAuthHandoff` ya se consume de forma atomica
- los eventos anonimos de `identity` ya no dependen de `aggregate_id` vacio
- los permisos efectivos ya salen deduplicados
- dashboard e inteligencia ahora exponen `projection_status`
- se limpio el mojibake de secciones historicas de documentacion

Archivos clave:
- [identity/eventing/models.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/models.py)
- [identity/eventing/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/services.py)
- [identity/users/views/auth.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views/auth.py)
- [identity/users/services/oauth_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/oauth_service.py)
- [identity/permissions/models/permission_grant.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/models/permission_grant.py)
- [identity/permissions/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/services.py)
- [finance/accounts/services/intelligence_dispatch_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/intelligence_dispatch_service.py)
- [identity/consents/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/services.py)
- [integrations_stub/banks/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/views.py)

#### OAuth Social Corregido
Flujo nuevo:
1. `GET /api/identity/users/auth/social/{provider}/start/`
2. proveedor externo redirige a `GET /api/identity/users/auth/social/{provider}/callback/`
3. ese callback solo valida y devuelve `handoff_code`
4. frontend llama `POST /api/identity/users/auth/social/exchange/`
5. ahi se crean `Device`, `UserSession` y los JWT

Esto reduce superficie de riesgo porque:
- no se emiten tokens sobre un callback `GET`
- el flujo queda mas facil de observar y controlar
- las respuestas sensibles salen con `Cache-Control: no-store`
- el handoff se invalida bajo transaccion y no debe poder consumirse dos veces en paralelo

#### Aggregate IDs En Identity
Decision aplicada:
- eventos con `user_id` usan `aggregate_type=identity_user`
- eventos con `entity_id` usan `aggregate_type=identity_<entity_type>`
- eventos pre-user, como social auth, usan `aggregate_type=identity_flow`
- si no existe un id natural, se usa un hash estable del payload/evento

Resultado:
- el outbox de `identity` ya no queda con `aggregate_id` vacio
- mejora filtros operativos, trazabilidad y coherencia con `accounts`

#### Permisos Derivados Vs Manuales
Antes:
- un grant de plan podia sobreescribir un override manual si compartian `permission_code` y scope

Ahora:
- la unicidad incluye `source` y `grant_kind`
- un entitlement por plan/consentimiento y un override manual pueden coexistir
- la lectura efectiva devuelve `permission_codes` deduplicados

#### Proyecciones Async
Decision operativa:
- en produccion, la inteligencia de `accounts` debe refrescarse por `Cloud Tasks` o worker
- el fallback local solo queda para desarrollo u operacion controlada

Endpoints afectados:
- `GET /api/identity/users/dashboard/`
- `POST /api/finance/accounts/portfolio-snapshots/refresh/` y equivalentes del set de inteligencia

Respuesta esperada:
- si la proyeccion no existe aun, el sistema puede responder con datos parciales o `202` y marcar que la proyeccion esta pendiente
- ademas ahora devuelve `projection_status` para exponer:
  - pending
  - cloud_tasks_ready
  - local_fallback_allowed
  - latest_generated_at
  - age_seconds

#### Consentimientos E Integraciones
Decision operativa:
- `identity.consents` ya no debe depender directamente del stub local como camino principal
- primero intenta un endpoint interno configurable
- solo si eso no existe o falla y el fallback esta habilitado, usa la implementacion local

Separacion de secretos:
- `ACCOUNTS_SYNC_INTERNAL_TOKEN`: sync de cuentas
- `IDENTITY_CONSENTS_INTERNAL_TOKEN`: teardown de consentimientos

Variables nuevas o relevantes:
- `IDENTITY_CONSENT_TEARDOWN_HANDLER_URL`
- `IDENTITY_CONSENTS_INTERNAL_TOKEN`
- `IDENTITY_CONSENT_LOCAL_FALLBACK_ENABLED`

#### Migraciones Nuevas De Este Ajuste
- [identity/eventing/migrations/0002_outbox_transport_fields.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/migrations/0002_outbox_transport_fields.py)
- [identity/social_identities/migrations/0002_social_auth_handoff.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/social_identities/migrations/0002_social_auth_handoff.py)
- [identity/permissions/migrations/0003_permission_scope_source_kind_constraint.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/migrations/0003_permission_scope_source_kind_constraint.py)

#### Validacion Hecha
Se valido en este entorno:
- compilacion sintactica con `py_compile` de los archivos criticos ajustados
- limpieza dirigida del mojibake historico en `documentacion.md` e `identity/documentacion.md`

No se pudo validar aqui:
- `manage.py check`
- migraciones ejecutadas
- login social contra Google/Facebook reales

Motivo:
- el interprete activo de este shell no tiene Django instalado ni el virtualenv del proyecto

### 18.14. Cierre Final De Coherencia Entre Identity Y Accounts

Se aplicaron estos ajustes finales:
- social auth queda alineado con Vexxo como modelo `frontend callback + backend exchange + backend emite eventos`
- `identity` ya tiene API operativa para su outbox
- los secretos internos de `sync`, `intelligence` y `consents` dejan de compartir fallback por defecto
- `permissions` ya resuelve precedencia efectiva entre `override`, `manual` y `entitlement`
- el catalogo de eventos expone mejor listeners efectivos y evita declarar listeners patron inexistentes

Archivos clave:
- [identity/users/services/oauth_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/oauth_service.py)
- [identity/users/views/auth.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views/auth.py)
- [identity/eventing/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/views.py)
- [identity/permissions/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/services.py)
- [finance/accounts/domain/events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/domain/events.py)
- [identity/users/domain/events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/domain/events.py)

Nuevo contrato social recomendado:
1. frontend pide `GET /api/identity/users/auth/social/{provider}/start/`
2. proveedor redirige al callback del frontend
3. frontend manda `provider`, `code`, `state` y `redirect_uri` a `POST /api/identity/users/auth/social/exchange/`
4. backend hace exchange real, vincula/crea usuario, registra dispositivo y sesion, y emite eventos `users.*`

Nuevos endpoints operativos de eventing:
- `/api/identity/eventing/outbox-identidad/`
- `/api/identity/eventing/outbox-identidad/health/`
- `/api/identity/eventing/outbox-identidad/contracts/`

Nuevas variables relevantes:
- `GOOGLE_OAUTH_FRONTEND_CALLBACK_URL`
- `FACEBOOK_OAUTH_FRONTEND_CALLBACK_URL`
- `ACCOUNTS_INTELLIGENCE_INTERNAL_TOKEN`
- `IDENTITY_CONSENTS_INTERNAL_TOKEN`

### 18.15. Deny Explicito En Permissions

Archivos:
- [identity/permissions/models/permission_grant.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/models/permission_grant.py)
- [identity/permissions/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/services.py)
- [identity/permissions/views/permission_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/views/permission_views.py)

Cambio aplicado:
- `PermissionStatus` ahora incluye `denied`
- un override manual puede negar una capability aunque el plan la otorgue
- la resolucion efectiva ya no es solo "cualquier grant granted habilita"
- ahora existe precedencia explicita de grant y de estado

Precedencia efectiva:
- `override`
- `manual`
- `entitlement`

Dentro de la misma prioridad:
- `denied`
- `granted`
- `revoked`
- `expired`

Endpoints relevantes:
- `POST /api/identity/permissions/grants/`
- `POST /api/identity/permissions/grants/{id}/deny/`
- `GET /api/identity/permissions/grants/effective/`

Evento nuevo:
- `users.permission.denied.v1`

### 18.16. Metricas Y Alertas Operativas De Proyecciones Async

Archivos:
- [finance/accounts/services/intelligence_health_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/intelligence_health_service.py)
- [finance/accounts/views/intelligence_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/views/intelligence_views.py)
- [identity/users/views/dashboard.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views/dashboard.py)
- [backend/settings.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/backend/settings.py)
- [.env](/c:/Users/Alamb/Documents/Vexxo_Backend_API/.env)

Que agrega:
- `projection_health` junto a `projection_status`
- thresholds operativos configurables
- deteccion de:
  - `pending_too_long`
  - `stale`
  - `pipeline_unavailable`
- alertas persistentes deduplicadas con `source=accounts.intelligence.health`

Variables nuevas:
- `ACCOUNTS_INTELLIGENCE_ALERTS_ENABLED`
- `ACCOUNTS_INTELLIGENCE_MAX_PENDING_SECONDS`
- `ACCOUNTS_INTELLIGENCE_STALE_AFTER_SECONDS`

Endpoints donde se refleja:
- `GET /api/identity/users/dashboard/`
- `GET /api/finance/accounts/snapshots-portafolio-cuenta/overview/`
- `GET /api/finance/accounts/snapshots-portafolio-cuenta/health/`
- `POST /api/finance/accounts/snapshots-portafolio-cuenta/refresh/`

Resultado:
- si una proyeccion async queda demasiado tiempo pendiente o stale
- el sistema ya no depende solo de logs manuales
- ahora expone salud operativa y puede dejar alerta persistente para seguimiento


