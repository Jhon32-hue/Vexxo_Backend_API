# Vexxo Backend API

## Que es

Este repositorio contiene el backend principal de Vexxo, una app financiera
personal mobile-first.

Su trabajo no es solo guardar CRUDs. El backend:

- entiende la realidad financiera del usuario
- aplica politicas de producto, riesgo y operacion
- orquesta eventos de dominio
- integra proveedores externos
- materializa ledger, proyecciones y experiencia realtime

La idea de negocio es simple:

- observar dinero
- interpretarlo
- ayudar a decidir
- ejecutar acciones financieras con seguridad operativa

## Core del negocio

Vexxo no se modela como un simple tracker.

Los bounded contexts principales responden a estas preguntas:

- `identity`: quien es el usuario, que plan tiene, que puede hacer
- `finance.accounts`: donde vive el dinero y quien puede operar cada cuenta
- `finance.transactions`: cual es el ledger real y sus efectos contables
- `payments`: como se ejecutan pagos externos sin contaminar el ledger
- `alerts`: que debe llamar la atencion del usuario y como se enriquece con IA
- `notifications` y `realtime`: como se entrega feedback util a mobile/web

## Arquitectura logica

Patrones principales del proyecto:

- BFF/API para mobile y web
- bounded contexts por dominio
- eventos de dominio con outbox
- workers y callbacks para procesos asincronos
- read models para lecturas operativas y UX
- separacion entre ejecucion externa y reflejo contable

Reglas estructurales importantes:

- pagar no es lo mismo que registrar una transaccion
- `Account.balance` es cache operativo, no ledger canonico
- la publicacion confiable usa outbox; la UX puede usar senales realtime livianas
- los requests web deben terminar rapido; el trabajo pesado se mueve a workers,
  callbacks o consumidores del bus

## Encaje con GCP

El backend esta pensado para una topologia cloud-first en GCP.

### Edge, API y seguridad

- API Gateway como entrada B2C
- Cloud Armor para WAF y DDoS
- Identity Platform o Firebase Auth para auth externa
- Cloud IAM para permisos de servicios
- Secret Manager para tokens, secretos y credenciales
- Cloud KMS para cifrado de material sensible

### Compute

- Cloud Run para:
  - `api` Django/DRF
  - `integrations_service`
  - `alerts_service`
  - `notifications_service`
  - `data_service`
  - `llm_gateway`
  - workers operativos
- Artifact Registry para imagenes
- Vertex AI o GKE/GPU cuando el serving de modelos lo exija

### Event-driven y jobs

- Pub/Sub como backbone de eventos externos
- Cloud Tasks para retries e idempotencia HTTP
- Cloud Scheduler para cron jobs
- Workflows cuando haga falta orquestacion multi-step

### Data

- Cloud SQL PostgreSQL para OLTP
- Cloud Storage para documentos, exports y artefactos
- BigQuery para analytics, datasets y exploracion
- Datastream y Dataflow para CDC y pipelines
- Dataplex/Data Catalog si se endurece gobierno de datos o B2B

### Observabilidad

- Cloud Logging
- Cloud Monitoring
- Cloud Trace
- Error Reporting
- OpenTelemetry si se profundiza tracing distribuido

### IA

- Gemini via `llm_gateway`
- Document AI si OCR pasa a ser core
- BigQuery ML para analitica y features

## Estructura fisica del backend

El repositorio mezcla bounded contexts de negocio, infraestructura compartida y
carpetas operativas de soporte.

### Carpetas raiz mas importantes

- `api/`
  BFF HTTP para mobile/web. Aqui vive la capa que expone endpoints, routers y
  versionado hacia clientes.
- `backend/`
  configuracion global de Django, settings, arranque y ensamblaje del proyecto.
- `common/`
  infraestructura compartida del monolito modular: eventos, helpers, piezas
  comunes y adaptadores transversales.
- `identity/`
  usuario, plan, permisos, consentimientos, sesiones, dispositivos e identidades
  externas.
- `finance/`
  cuentas, ledger, deudas, categorias, vendors, FX y otros contextos
  financieros.
- `payments/`
  ejecucion externa de pagos, payout/dispersions, contratos por proveedor y
  scheduling de pagos.
- `alerts/`
  alertas, reglas y enriquecimiento con IA.
- `notifications/`
  inbox durable y piezas de entrega de notificaciones.
- `realtime/`
  señales livianas para polling y futura capa realtime viva.
- `reports/`
  reporting agregado, summaries y contextos reservados para snapshots y exports.
- `planning/`
  metas y contextos futuros de planning mas avanzado.
- `documents/`
  bloque documental pensado para storage, metadata, OCR y vinculos contables.
- `contacts/`
  contactos financieros reutilizables del usuario.
- `social/`
  contextos de colaboracion social; hoy `teams` es el mas concreto.
- `support/`
  auditoria funcional y piezas de soporte operativo.
- `integrations_stub/`
  fronteras temporales de integracion mientras ciertos servicios aun no se
  separan en microservicios o workers externos.

### Carpetas de soporte y operacion

- `observability/`
  configuracion o piezas relacionadas con logging, metricas o salud operativa.
- `security/`
  piezas transversales de seguridad del proyecto.
- `tasks/`
  scripts o entrypoints para trabajos de fondo si aplica.
- `scripts/`
  comandos de soporte, bootstrap o automatizacion local.
- `tests/`
  pruebas transversales o de integracion a nivel repositorio.
- `admin_tools/`
  herramientas internas de operacion y administracion.
- `docs/`
  documentacion adicional no canónica del dominio.
- `logs/`, `media/`, `staticfiles/`
  artefactos locales del entorno de ejecucion.

## Mapa funcional por dominio

El sistema esta organizado para que cada bloque responda a una responsabilidad
de negocio clara.

### `identity`

Define quien es el usuario, bajo que plan opera y que puede hacer.

Incluye:

- `users`: plan, capabilities, usage projection y politica de producto
- `permissions`: grants efectivos y entitlements derivados
- `consents`: permisos legales u operativos para integraciones
- `devices` y `sessions`: seguridad operacional del acceso
- `social_identities`: vinculacion con identidades externas
- `eventing`: outbox y read models propios del contexto

Su rol en el sistema es transversal: casi todos los modulos consultan plan,
ownership o permisos resueltos por identidad.

### `finance`

Es el corazon financiero interno del usuario.

Incluye:

- `accounts`: cuentas, sharing, sync, balances cacheados y politica de acceso
- `transactions`: ledger canonico y participantes
- `debts`: deudas y cuotas
- `categories`, `vendors`, `fx`: catalogos y datos auxiliares del ledger
- `budgets`, `investments`, `limits`: contextos hoy menos maduros o reservados

La idea clave es que `transactions` representa verdad contable, mientras que
`accounts` aporta vistas operativas y relaciones de colaboracion.

### `payments`

Separa ejecucion financiera externa del ledger interno.

Incluye:

- `payment_intents`: intentos de pago, callbacks, pricing, payout, settlement,
  adapters y contratos por proveedor
- `scheduled_payments`: planificacion y recurrencia
- otros submodulos como `calendar` o `reminders`, que preparan la capa de
  programacion de pagos

`payments` no reemplaza al ledger. Cuando un pago externo se confirma, su
reflejo final se materializa en `finance.transactions`.

### `alerts`

Se encarga de detectar o expresar cosas que merecen atencion del usuario.

Incluye:

- `alerts`: alerta visible y enriquecimiento
- `rules`: automatizacion configurable por usuario
- `triggers`, `listeners`, `ai_stub`: contextos reservados para evolucion

Es el puente entre datos financieros y explicacion accionable.

### `notifications` y `realtime`

Resuelven como se entrega feedback sin mezclarlo con el core transaccional.

- `notifications.deliveries`: inbox durable
- `notifications.listeners`: transforma eventos del dominio en mensajes
- `notifications.preferences` y `templates`: contexto reservado para control y
  contenido de entrega
- `realtime.consumers`: persiste `RealtimeSignal` para polling o gateways
  futuros

La regla general es:

- inbox durable para historial y soporte
- realtime liviano para UX interactiva

### `reports` y `planning`

Sostienen interpretacion, resumen y futuro del dinero.

- `reports.reports`: agregaciones simples sobre el ledger
- `reports.summaries`: resumenes reservados o en evolucion
- `reports.exports`, `monthly_reports`, `snapshots`: contextos preparados para
  reporting persistido
- `planning.goals`: metas financieras
- `planning.milestones`, `projections`, `shared_goals`: capa futura de planning
  mas rica

### `documents`, `contacts` y `social`

Son bloques complementarios al core financiero.

- `documents`: documentos, metadata, OCR y storage, hoy mayormente reservados
- `contacts`: contactos financieros reutilizables y balance neto por contraparte
- `social`: colaboracion general; hoy `teams` es la pieza mas concreta

### `support`, `common`, `integrations_stub`

Resuelven soporte transversal.

- `support.audit`: auditoria funcional
- `common`: eventos, helpers y piezas de infraestructura transversal
- `integrations_stub`: adapters temporales y workers aun no extraidos

## Como se relacionan entre si

El valor del sistema no esta en cada modulo aislado, sino en la forma en que
se conectan.

### Relacion estructural principal

- `identity.users` define plan y capabilities
- `identity.permissions` traduce eso en grants operativos
- `finance.accounts`, `payments`, `alerts.rules` y `contacts` aplican guards
  usando ese contexto
- `common.domain_events` y los outbox de cada contexto desacoplan fan-out y
  trabajo asincrono
- `notifications`, `realtime` y ciertos read models consumen esos eventos para
  UX y soporte

### Flujo tipico de dinero dentro de Vexxo

1. el usuario se autentica y entra con su contexto de plan/capabilities
2. consulta cuentas y balances operativos desde `finance.accounts`
3. registra o recibe movimientos en `finance.transactions`
4. `accounts` actualiza vistas operativas y emite eventos
5. alertas, notificaciones, realtime y proyecciones reaccionan
6. si el usuario ejecuta un pago externo, eso nace en `payments`
7. cuando el rail externo confirma el pago, el reflejo final se materializa en
   `finance.transactions`

### Flujo de politica de producto

1. `identity.users` resuelve plan y usage projection
2. un modulo operativo intenta ejecutar una accion:
   - conectar cuenta
   - crear regla
   - iniciar pago
   - agregar contacto
3. el guard local consulta capacidades y uso
4. si procede, se persiste el cambio
5. los eventos emitidos actualizan proyecciones o UX

### Flujo de integracion externa

1. el BFF recibe la solicitud del usuario
2. el bounded context correspondiente persiste su estado local y encola evento
3. el outbox publica a consumidores o workers
4. un servicio externo, adapter o callback devuelve resultado
5. el contexto aplica la respuesta y vuelve a emitir eventos
6. el sistema actualiza ledger, inbox, realtime o soporte segun corresponda

## Que hace cada bloque de cara al cliente

Visto desde producto, los modulos cumplen funciones diferentes:

- `identity`
  hace que el usuario exista, pueda entrar y tenga una experiencia coherente con
  su plan.
- `finance.accounts`
  le dice al usuario donde vive su dinero y con quien lo comparte.
- `finance.transactions`
  representa el historial financiero real que sostiene reportes y balances.
- `payments`
  permite ejecutar pagos externos sin ensuciar la verdad contable.
- `alerts`
  convierte datos en atencion y decisiones.
- `notifications` y `realtime`
  hacen que el usuario reciba feedback entendible y a tiempo.
- `reports` y `planning`
  ayudan a resumir el pasado y preparar decisiones futuras.
- `contacts`, `social`, `documents`
  enriquecen el contexto humano y operativo alrededor del dinero.

## Principios de modelado del backend

Estos principios explican por que el proyecto esta organizado asi:

- un contexto de negocio no debe absorber responsabilidades de otro
- el ledger no debe mezclarse con ejecucion externa de PSPs
- los requests web deben ser cortos y predecibles
- la consistencia operativa fuerte viaja por outbox y consumidores
- la experiencia del cliente puede usar señales livianas adicionales
- los README especificos deben reflejar el estado actual real, no un roadmap
  inventado

## Mapa de documentacion canonica

La documentacion ya no vive en un documento gigante mezclado. Cada modulo debe
documentar su estado actual, flujos, casos de uso y relaciones.

Documentos principales:

- [backend/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/backend/README.md)
  Configuracion global de Django, settings, URLs y entrypoints del proyecto.
- [common/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/common/README.md)
  Infraestructura transversal, bus de eventos y encaje con Pub/Sub.
- [api/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/api/README.md)
  Superficie HTTP, versionado y rol del BFF.
- [api/v1/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/api/v1/README.md)
  Capa versionada principal de routers y endpoints HTTP.
- [api/throttling/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/api/throttling/README.md)
  Frontera tecnica para rate limiting y proteccion de consumo.
- [finance/accounts/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/README.md)
  Dominio de cuentas, sharing, balances, outbox, sync e inteligencia derivada.
- [identity/users/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/README.md)
  Usuario, planes, capabilities, usage projection y politica de producto.
- [identity/eventing/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/README.md)
  Outbox y read models de identidad.
- [identity/permissions/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/README.md)
  Entitlements, grants efectivos y resolucion de permisos.
- [identity/consents/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/README.md)
  Consentimientos legales, operativos y teardown de integraciones.
- [identity/devices/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/devices/README.md)
  Registro, confianza y revocacion de dispositivos.
- [identity/sessions/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/README.md)
  Operacion de sesiones y controles de seguridad del usuario.
- [identity/social_identities/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/social_identities/README.md)
  Identidades sociales vinculadas y handoffs de autenticacion externa.
- [alerts/alerts/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/alerts/README.md)
  Alertas, enriquecimiento y frontera con IA.
- [alerts/rules/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/rules/README.md)
  Reglas de alerta y gating de automatizacion por plan.
- [alerts/triggers/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/triggers/README.md)
  Contexto reservado para disparadores de alertas.
- [alerts/listeners/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/listeners/README.md)
  Contexto reservado para listeners especializados de alertas.
- [alerts/ai_stub/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/ai_stub/README.md)
  Frontera temporal o placeholder para integracion IA stub.
- [notifications/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/README.md)
  Inbox persistente y listeners de entrega.
- [notifications/deliveries/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/deliveries/README.md)
  Materializacion durable del inbox de usuario.
- [notifications/preferences/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/preferences/README.md)
  Preferencias de entrega y control por canal del usuario.
- [notifications/templates/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/templates/README.md)
  Contexto reservado para plantillas de notificacion.
- [notifications/listeners/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/listeners/README.md)
  Listeners que convierten eventos de dominio en inbox durable.
- [realtime/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/realtime/README.md)
  Senales livianas para polling y futura capa realtime viva.
- [realtime/consumers/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/realtime/consumers/README.md)
  Persistencia y API de `RealtimeSignal`.
- [payments/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/payments/README.md)
  Vision general de pagos, scheduling y relacion con ledger.
- [payments/payment_intents/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/payments/payment_intents/README.md)
  Intents, callbacks, settlement, contratos por proveedor y payout.
- [payments/scheduled_payments/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/payments/scheduled_payments/README.md)
  Planificacion recurrente o programada.
- [payments/reminders/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/payments/reminders/README.md)
  Contexto reservado para recordatorios de pago.
- [payments/calendar/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/payments/calendar/README.md)
  Contexto reservado para organizacion temporal o calendario de pagos.
- [finance/transactions/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/transactions/README.md)
  Ledger, materializacion contable y relacion con pagos externos.
- [finance/categories/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/categories/README.md)
  Catalogo de categorias y semantica de gasto/ingreso.
- [finance/vendors/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/vendors/README.md)
  Contrapartes y comercios reutilizables en ledger y pagos.
- [finance/debts/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/debts/README.md)
  Deudas y cuotas como obligaciones financieras.
- [finance/fx/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/fx/README.md)
  Snapshots de tasas de cambio y soporte multicurrency.
- [finance/budgets/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/budgets/README.md)
  Contexto reservado para presupuestos y control de gasto futuro.
- [finance/investments/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/investments/README.md)
  Contexto reservado para posiciones y producto de inversion.
- [finance/limits/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/limits/README.md)
  Contexto reservado para limites financieros transversales.
- [planning/goals/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/planning/goals/README.md)
  Metas financieras y capa de planning.
- [planning/milestones/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/planning/milestones/README.md)
  Contexto reservado para hitos de planning.
- [planning/projections/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/planning/projections/README.md)
  Contexto reservado para escenarios y proyecciones futuras.
- [planning/shared_goals/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/planning/shared_goals/README.md)
  Contexto reservado para metas compartidas.
- [contacts/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/contacts/README.md)
  Contactos financieros reutilizables y balance neto por contraparte.
- [documents/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/documents/README.md)
  Vision general del bounded context documental.
- [social/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/social/README.md)
  Panorama del bloque social y su nivel de madurez actual.
- [social/teams/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/social/teams/README.md)
  Equipos y membresias sociales generales.
- [reports/reports/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/reports/reports/README.md)
  Reportes agregados simples sobre el ledger.
- [reports/summaries/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/reports/summaries/README.md)
  Espacio reservado para resumenes agregados y snapshots de reporting.
- [reports/exports/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/reports/exports/README.md)
  Contexto reservado para exportaciones y artefactos de reportes.
- [reports/monthly_reports/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/reports/monthly_reports/README.md)
  Contexto reservado para cierres o reportes mensuales persistidos.
- [reports/snapshots/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/reports/snapshots/README.md)
  Contexto reservado para snapshots de reporting.
- [integrations_stub/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/README.md)
  Fronteras temporales para workers e integraciones aun no separadas.
- [integrations_stub/banks/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/README.md)
  Sync e integraciones bancarias temporales.
- [tasks/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/tasks/README.md)
  Estructura general de ejecucion asincrona, scheduling y workers.
- [tasks/dispatchers/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/tasks/dispatchers/README.md)
  Frontera preparada para dispatch a Cloud Tasks, Pub/Sub o Scheduler.
- [tasks/scheduled/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/tasks/scheduled/README.md)
  Contexto reservado para jobs programados y periodicos.
- [tasks/listeners/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/tasks/listeners/README.md)
  App reservada para listeners tecnicos o de trabajo asincrono.
- [tasks/workers/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/tasks/workers/README.md)
  App reservada para workers genericos del sistema.
- [security/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/security/README.md)
  Frontera transversal para politicas de seguridad, fraude y proteccion de datos.
- [observability/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/observability/README.md)
  Frontera para salud, metricas, logging y tracing del sistema.
- [scripts/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/scripts/README.md)
  Utilidades operativas, bootstrap y backfills fuera del request path.
- [admin_tools/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/admin_tools/README.md)
  Herramientas internas de operacion, soporte y revision manual.
- [support/audit/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/support/audit/README.md)
  Auditoria funcional y trazabilidad de negocio.
- [support/access_history/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/support/access_history/README.md)
  Contexto reservado para historial de acceso y soporte operativo.
- [support/consent_audit/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/support/consent_audit/README.md)
  Contexto reservado para trazabilidad de consentimientos.
- [support/support_views/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/support/support_views/README.md)
  Contexto reservado para vistas o endpoints internos de soporte.

## Como leer el sistema

Si quieres entender el backend rapido, este es el orden recomendado:

1. `identity.users`
2. `finance.accounts`
3. `finance.transactions`
4. `payments`
5. `alerts`
6. `notifications` y `realtime`

## Estado de la documentacion

Principio vigente:

- importa el estado actual del sistema
- no interesa una cronologia larga de cambios
- cada README debe explicar:
  - proposito
  - conceptos
  - casos de uso
  - relaciones
  - flujo tecnico
  - impacto de negocio
  - encaje con GCP cuando aplique

Si aparece documentacion detallada transversal, debe resumirse aqui y
segmentarse de nuevo en el modulo correcto.
