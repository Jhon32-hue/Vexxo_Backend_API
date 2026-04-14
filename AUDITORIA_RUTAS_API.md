# Auditoria de rutas API

## Objetivo

Esta auditoria revisa la superficie HTTP real del backend de Vexxo:

- consistencia de prefijos
- permisos y autenticacion
- separacion entre rutas publicas e internas
- consistencia entre la documentacion y el codigo
- riesgos operativos para cloud y API Gateway

## Resumen ejecutivo

Estado general despues de la correccion:

- la superficie HTTP sigue bien agrupada por bounded context
- el router principal versionado en `/api/` sigue centralizado
- ya existe una familia canonica de rutas internas bajo `/api/internal/...`
- los endpoints internos endurecidos ahora fallan cerrado si falta su token

La deuda que sigue abierta ya no es de exposicion directa, sino de transicion:

1. migrar callers a los prefijos internos canonicos
2. retirar rutas legacy compatibles cuando ya no se usen
3. seguir homogenizando naming y semantica de rutas

## Hallazgos

### Resuelto: `payments/worker-report` ya no queda abierto si falta el token interno

En [payments/payment_intents/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/payments/payment_intents/views.py), `PaymentWorkerReportView` ahora usa validacion comun de token interno y falla cerrado si `PAYMENTS_INTERNAL_TOKEN` no esta configurado.

Rutas actuales:

- `/api/payments/intents/worker-report/`
- `/api/internal/payments/worker-report/`

Estado:

- corregido
- se agrego ruta canonica interna
- la ruta antigua sigue viva por compatibilidad

### Resuelto: `alerts/internal/ai-worker` ya no queda abierto si falta el token interno

En [alerts/alerts/views/alert_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/alerts/views/alert_views.py), `AlertAiWorkerView` ahora usa la misma validacion comun de token interno y falla cerrado.

Rutas actuales:

- `/api/alerts/internal/ai-worker/`
- `/api/internal/alerts/ai-worker/`

Estado:

- corregido
- se agrego ruta canonica interna
- la ruta antigua sigue viva por compatibilidad

### Mejorado: callbacks de sync de `accounts` ya tienen ruta interna canonica y token obligatorio

Las acciones:

- `mark_sync_running`
- `mark_sync_success`
- `mark_sync_error`
- `mark_sync_stale`

siguen existiendo en [finance/accounts/views/account_action_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/views/account_action_handlers.py), pero ahora requieren token interno. Ademas existe una ruta canonica nueva en [finance/accounts/internal_urls.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/internal_urls.py).

Rutas actuales:

- `/api/finance/accounts/cuentas/{id}/mark_sync_running/`
- `/api/finance/accounts/cuentas/{id}/mark_sync_success/`
- `/api/finance/accounts/cuentas/{id}/mark_sync_error/`
- `/api/finance/accounts/cuentas/{id}/mark_sync_stale/`
- `/api/internal/accounts/{account_id}/sync/running/`
- `/api/internal/accounts/{account_id}/sync/success/`
- `/api/internal/accounts/{account_id}/sync/error/`
- `/api/internal/accounts/{account_id}/sync/stale/`

Estado:

- mejorado
- ya no dependen solo de `IsAuthenticated`
- existe ruta canonica interna
- sigue habiendo deuda de limpieza mientras vivan las rutas antiguas

### Mejorado: la estrategia de prefijos internos ya tiene familia canonica `/api/internal/...`

Hoy existe una familia canonica bajo `/api/internal/...`, aunque siguen vivas algunas rutas legacy compatibles:

- `/api/internal/accounts/...`
- `/api/internal/transactions/...`
- `/api/internal/payments/...`
- `/api/internal/alerts/...`
- `/api/internal/integrations/banks/...`

Referencias:

- [api/v1/routers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/api/v1/routers.py)
- [backend/urls.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/backend/urls.py)
- [finance/accounts/internal_urls.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/internal_urls.py)
- [finance/transactions/internal_urls.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/transactions/internal_urls.py)
- [payments/payment_intents/internal_urls.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/payments/payment_intents/internal_urls.py)
- [alerts/alerts/internal_urls.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/alerts/alerts/internal_urls.py)

Estado:

- mejorado
- quedan aliases legacy para no romper operacion durante la migracion

### Resuelto: `support.audit` ahora soporta lectura global para staff

En [support/audit/views/audit_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/support/audit/views/audit_views.py), `AuditoriaViewSet` sigue usando `IsAuthenticated`, pero ahora:

- si el usuario es staff, puede consultar globalmente
- si no lo es, sigue viendo solo su propia auditoria
- staff puede filtrar por `user_id`

Ruta afectada:

- `/api/support/audit/auditoria/`

Estado:

- corregido a un punto medio operativo razonable

### Resuelto: habia inconsistencias reales entre la documentacion y el codigo

Quedaron corregidas en [RUTAS_API.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/RUTAS_API.md):

- `auth/social/{provider}/callback/` ahora figura solo como `GET`
- `auth/social/{provider}/unlink/` ahora figura como `DELETE`
- `payments` internos distinguen ruta canonica y ruta legacy
- `support.audit` ya refleja su alcance real
- `accounts mark_sync_*` ya aparece como callback legacy compatible

## Lo que esta bien

- `api/v1/routers.py` centraliza bien la composicion principal
- `transactions` sigue con frontera interna clara bajo `/api/internal/transactions/`
- los routers por bounded context son legibles y relativamente estables
- [RUTAS_API.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/RUTAS_API.md) ya sirve como mapa canonico de superficie HTTP

## Prioridades recomendadas

### Fase 1

- migrar callers internos al prefijo canonico `/api/internal/...`

### Fase 2

- retirar rutas legacy compatibles cuando ya no se consuman

### Fase 3

- seguir alineando naming y semantica de rutas de soporte, admin e internas
- mantener `RUTAS_API.md` como documento canonico de superficie HTTP

## Principio rector

La superficie HTTP debe seguir el mismo principio que el eventing cloud:

- homogeneidad
- separacion clara entre negocio e integraciones
- fail-closed en rutas internas
- ownership explicito por bounded context



## Addendum 2026-04 Integraciones, Intake Y Contratos

Rutas internas/documentos que deben considerarse parte del estado actual del
backend:

### Transactions intake

- `POST /api/internal/transactions/intake/batches/`
- `POST /api/internal/transactions/intake/batches/{id}/apply/`
- `POST /api/internal/transactions/intake/row/`
- `POST /api/internal/transactions/intake/message/`
- `POST /api/internal/transactions/intake/reconcile/`
- `POST /api/internal/transactions/reconciliation/issues/{id}/resolve/`

### Implicaciones de auditoria

- `POST /api/internal/transactions/intake/message/` ya existe y soporta
  `message_inferred.normalized_payload`
- el parser de mensajes ya no es solo una idea documental; es parte del
  runtime de `transactions`
- `TransactionExternalDetails` ya es pieza canonica del modulo
- `payment_execution` y `payment_reflection` no deben auditarse como si fueran
  la misma frontera

### Documentos canonicos a cruzar durante auditoria

- [INTEGRATION_SOURCE_CATALOG.md](/D:/Vexxo_Backend_API/INTEGRATION_SOURCE_CATALOG.md)
- [finance/transactions/RAIL_NORMALIZATION_CONTRACTS.md](/D:/Vexxo_Backend_API/finance/transactions/RAIL_NORMALIZATION_CONTRACTS.md)
- [payments/payment_intents/PAYMENT_EXECUTION_CONTRACTS.md](/D:/Vexxo_Backend_API/payments/payment_intents/PAYMENT_EXECUTION_CONTRACTS.md)
- [integrations/README.md](/D:/Vexxo_Backend_API/integrations/README.md)

