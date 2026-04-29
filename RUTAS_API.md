# Rutas API de Vexxo

## Que es este documento

Este documento concentra las rutas HTTP disponibles hoy en el backend de
Vexxo, agrupadas por modulo.

Su objetivo es servir como mapa rapido para:

- explorar el API en desarrollo
- probar endpoints en Postman
- entender el CRUD y las acciones custom de cada bounded context
- distinguir rutas publicas, autenticadas, administrativas e internas

## Convenciones

- prefijo publico principal: `/api/`
- prefijo interno de intake y reconciliacion de transactions:
  `/api/internal/transactions/`
- prefijo canonico interno actual: `/api/internal/...`
- el prefijo antiguo `/internal/integrations/banks/` sigue vivo por
  compatibilidad
- `Bearer`: requiere `Authorization: Bearer <access_token>`
- `Internal token`: requiere `X-Vexxo-Internal-Token`
- varios endpoints internos tambien esperan `X-Request-Id` y, para batches,
  `Idempotency-Key`
- `CRUD estandar DRF`: lista, crea, detalle, actualiza y elimina

## Entrada principal

### Backend root

| Ruta | Metodos | Uso |
|---|---|---|
| `/admin/` | `GET` | Admin de Django |
| `/api/` | varios | API principal versionada |
| `/api/internal/integrations/banks/` | varios | prefijo canonico interno del stub de integraciones |
| `/api/internal/integrations/llm/` | varios | prefijo canonico interno del stub LLM |
| `/internal/integrations/banks/` | varios | Puente interno temporal para integraciones |
| `/internal/integrations/llm/` | varios | Puente interno temporal para inferencia LLM |

## Identity

### identity.users

Base: `/api/identity/users/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/identity/users/auth/register/` | `POST` | publico | registro de usuario |
| `/api/identity/users/auth/login/` | `POST` | publico | login y emision de JWT |
| `/api/identity/users/auth/refresh/` | `POST` | publico con refresh token | renovar access token |
| `/api/identity/users/auth/logout/` | `POST` | `Bearer` | logout y revocacion |
| `/api/identity/users/auth/social/providers/` | `GET` | publico | listar proveedores sociales disponibles |
| `/api/identity/users/auth/social/exchange/` | `POST` | publico | exchange de credenciales sociales |
| `/api/identity/users/auth/social/{provider}/start/` | `GET` | publico | iniciar flujo social |
| `/api/identity/users/auth/social/{provider}/callback/` | `GET` | publico | callback del proveedor social |
| `/api/identity/users/auth/social/identities/` | `GET` | `Bearer` | listar identidades sociales vinculadas |
| `/api/identity/users/auth/social/{provider}/unlink/` | `DELETE` | `Bearer` | desvincular identidad social |
| `/api/identity/users/me/` | `GET` | `Bearer` | perfil y estado del usuario actual |
| `/api/identity/users/onboarding/complete/` | `POST` | `Bearer` | marcar onboarding como completado |
| `/api/identity/users/dashboard/` | `GET` | `Bearer` | dashboard agregado de usuario |
| `/api/identity/users/event-contract/` | `GET` | `Bearer` | contrato de eventos de identity/users |

### identity.users admin

Base: `/api/identity/users/admin/users/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/identity/users/admin/users/` | `GET` | staff/admin | listar usuarios |
| `/api/identity/users/admin/users/` | `POST` | staff/admin | crear usuario desde admin API |
| `/api/identity/users/admin/users/{id}/` | `GET` | staff/admin | detalle de usuario |
| `/api/identity/users/admin/users/{id}/` | `PUT`, `PATCH` | staff/admin | actualizar usuario |
| `/api/identity/users/admin/users/{id}/` | `DELETE` | staff/admin | eliminar usuario |
| `/api/identity/users/admin/users/{id}/set_plan/` | `POST` | staff/admin | cambiar plan |
| `/api/identity/users/admin/users/{id}/suspend/` | `POST` | staff/admin | suspender usuario |
| `/api/identity/users/admin/users/{id}/activate/` | `POST` | staff/admin | activar usuario |
| `/api/identity/users/admin/users/{id}/verify/` | `POST` | staff/admin | verificar usuario |

### identity.devices

Base: `/api/identity/devices/dispositivos/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/identity/devices/dispositivos/` | `GET` | `Bearer` | listar dispositivos |
| `/api/identity/devices/dispositivos/` | `POST` | `Bearer` | crear o registrar dispositivo |
| `/api/identity/devices/dispositivos/{id}/` | `GET` | `Bearer` | detalle de dispositivo |
| `/api/identity/devices/dispositivos/register_device/` | `POST` | `Bearer` | registrar dispositivo explicitamente |
| `/api/identity/devices/dispositivos/{id}/trust_device/` | `POST` | `Bearer` | marcar dispositivo como confiable |
| `/api/identity/devices/dispositivos/{id}/revoke/` | `POST` | `Bearer` | revocar dispositivo |
| `/api/identity/devices/dispositivos/suspicious/` | `GET` | staff/admin | listar dispositivos sospechosos |
| `/api/identity/devices/dispositivos/summary/` | `GET` | `Bearer` | resumen de dispositivos |

### identity.sessions

Base: `/api/identity/sessions/sesiones/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/identity/sessions/sesiones/` | `GET` | `Bearer` | listar sesiones |
| `/api/identity/sessions/sesiones/{id}/` | `GET` | `Bearer` | detalle de sesion |
| `/api/identity/sessions/sesiones/register_session/` | `POST` | `Bearer` | registrar sesion |
| `/api/identity/sessions/sesiones/{id}/revoke/` | `POST` | `Bearer` | revocar sesion |
| `/api/identity/sessions/sesiones/{id}/touch/` | `POST` | `Bearer` | refrescar actividad |
| `/api/identity/sessions/sesiones/active/` | `GET` | `Bearer` | listar sesiones activas |
| `/api/identity/sessions/sesiones/revoke_all/` | `POST` | `Bearer` | revocar todas |
| `/api/identity/sessions/sesiones/revoke_others/` | `POST` | `Bearer` | revocar otras sesiones |
| `/api/identity/sessions/sesiones/revoke_family/` | `POST` | `Bearer` | revocar familia de tokens |
| `/api/identity/sessions/sesiones/summary/` | `GET` | `Bearer` | resumen de sesiones |

### identity.consents

Base: `/api/identity/consents/consentimientos/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/identity/consents/consentimientos/` | `GET` | `Bearer` | listar consentimientos |
| `/api/identity/consents/consentimientos/` | `POST` | `Bearer` | crear consentimiento |
| `/api/identity/consents/consentimientos/{id}/` | `GET` | `Bearer` | detalle de consentimiento |
| `/api/identity/consents/consentimientos/grant/` | `POST` | `Bearer` | otorgar consentimiento |
| `/api/identity/consents/consentimientos/{id}/revoke/` | `POST` | `Bearer` | revocar consentimiento |
| `/api/identity/consents/consentimientos/active/` | `GET` | `Bearer` | listar consentimientos activos |
| `/api/identity/consents/consentimientos/expiring/` | `GET` | `Bearer` | listar por vencer |
| `/api/identity/consents/consentimientos/summary/` | `GET` | `Bearer` | resumen de consentimientos |

### identity.permissions

Base: `/api/identity/permissions/grants/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/identity/permissions/grants/` | `GET` | `Bearer` | listar grants |
| `/api/identity/permissions/grants/` | `POST` | staff/admin | crear grant |
| `/api/identity/permissions/grants/{id}/` | `GET` | `Bearer` | detalle de grant |
| `/api/identity/permissions/grants/{id}/revoke/` | `POST` | staff/admin | revocar grant |
| `/api/identity/permissions/grants/{id}/deny/` | `POST` | staff/admin | denegar grant |
| `/api/identity/permissions/grants/mine/` | `GET` | `Bearer` | grants del usuario actual |
| `/api/identity/permissions/grants/summary/` | `GET` | `Bearer` | resumen de grants |
| `/api/identity/permissions/grants/effective/` | `GET` | `Bearer` | grants efectivos |

### identity.eventing

Base: `/api/identity/eventing/outbox-identidad/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/identity/eventing/outbox-identidad/` | `GET` | staff/admin | listar outbox de identity |
| `/api/identity/eventing/outbox-identidad/{id}/` | `GET` | staff/admin | detalle de evento |
| `/api/identity/eventing/outbox-identidad/{id}/publish_now/` | `POST` | staff/admin | publicar ahora |
| `/api/identity/eventing/outbox-identidad/{id}/retry/` | `POST` | staff/admin | reintentar evento |
| `/api/identity/eventing/outbox-identidad/{id}/release_lock/` | `POST` | staff/admin | liberar lock |
| `/api/identity/eventing/outbox-identidad/health/` | `GET` | staff/admin | salud del outbox |
| `/api/identity/eventing/outbox-identidad/contracts/` | `GET` | staff/admin | contratos y governance de eventos |

## Finance accounts

### cuentas

Base: `/api/finance/accounts/cuentas/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/accounts/cuentas/` | `GET` | `Bearer` | listar cuentas |
| `/api/finance/accounts/cuentas/` | `POST` | `Bearer` | crear cuenta |
| `/api/finance/accounts/cuentas/{id}/` | `GET` | `Bearer` | detalle de cuenta |
| `/api/finance/accounts/cuentas/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar cuenta |
| `/api/finance/accounts/cuentas/{id}/` | `DELETE` | `Bearer` | eliminar cuenta |
| `/api/finance/accounts/cuentas/{id}/set_primary/` | `POST` | `Bearer` | marcar cuenta primaria |
| `/api/finance/accounts/cuentas/{id}/recalc_balance/` | `POST` | `Bearer` | recalcular balance |
| `/api/finance/accounts/cuentas/{id}/freeze/` | `POST` | `Bearer` | congelar cuenta |
| `/api/finance/accounts/cuentas/{id}/unfreeze/` | `POST` | `Bearer` | descongelar cuenta |
| `/api/finance/accounts/cuentas/{id}/archive/` | `POST` | `Bearer` | archivar cuenta |
| `/api/finance/accounts/cuentas/{id}/unarchive/` | `POST` | `Bearer` | desarchivar cuenta |
| `/api/finance/accounts/cuentas/{id}/close_account/` | `POST` | `Bearer` | cerrar cuenta |
| `/api/finance/accounts/cuentas/summary/` | `GET` | `Bearer` | resumen de cuentas |
| `/api/finance/accounts/cuentas/{id}/members/` | `GET` | `Bearer` | listar miembros de una cuenta |
| `/api/finance/accounts/cuentas/{id}/link_external_source/` | `POST` | `Bearer` | vincular fuente externa |
| `/api/finance/accounts/cuentas/{id}/unlink_external_source/` | `POST` | `Bearer` | desvincular fuente externa |
| `/api/finance/accounts/cuentas/{id}/schedule_sync/` | `POST` | `Bearer` | agendar sync |
| `/api/finance/accounts/cuentas/{id}/mark_sync_running/` | `POST` | `Internal token` | callback legacy compatible de sync running |
| `/api/finance/accounts/cuentas/{id}/mark_sync_success/` | `POST` | `Internal token` | callback legacy compatible de sync success |
| `/api/finance/accounts/cuentas/{id}/mark_sync_error/` | `POST` | `Internal token` | callback legacy compatible de sync error |
| `/api/finance/accounts/cuentas/{id}/mark_sync_stale/` | `POST` | `Internal token` | callback legacy compatible de sync stale |
| `/api/finance/accounts/cuentas/plan_usage/` | `GET` | `Bearer` | uso del plan en cuentas |
| `/api/finance/accounts/cuentas/sync_overview/` | `GET` | `Bearer` | overview de sync |
| `/api/finance/accounts/cuentas/operational_overview/` | `GET` | `Bearer` | overview operativo |
| `/api/finance/accounts/cuentas/event_contract/` | `GET` | `Bearer` | contrato de eventos de accounts |

### membresias-cuenta

Base: `/api/finance/accounts/membresias-cuenta/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/accounts/membresias-cuenta/` | `GET` | `Bearer` | listar membresias |
| `/api/finance/accounts/membresias-cuenta/` | `POST` | `Bearer` | crear membresia o invitacion |
| `/api/finance/accounts/membresias-cuenta/{id}/` | `GET` | `Bearer` | detalle de membresia |
| `/api/finance/accounts/membresias-cuenta/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar membresia |
| `/api/finance/accounts/membresias-cuenta/{id}/` | `DELETE` | `Bearer` | eliminar o revocar membresia |
| `/api/finance/accounts/membresias-cuenta/{id}/accept_invitation/` | `POST` | `Bearer` | aceptar invitacion |
| `/api/finance/accounts/membresias-cuenta/{id}/revoke/` | `POST` | `Bearer` | revocar membresia |
| `/api/finance/accounts/membresias-cuenta/{id}/rotate_invitation/` | `POST` | `Bearer` | reemitir invitacion |

### snapshots-balance

Base: `/api/finance/accounts/snapshots-balance/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/accounts/snapshots-balance/` | `GET` | `Bearer` | listar snapshots de balance |
| `/api/finance/accounts/snapshots-balance/` | `POST` | `Bearer` | crear snapshot manual |
| `/api/finance/accounts/snapshots-balance/{id}/` | `GET` | `Bearer` | detalle de snapshot |
| `/api/finance/accounts/snapshots-balance/latest/` | `GET` | `Bearer` | ultimo snapshot por cuenta |
| `/api/finance/accounts/snapshots-balance/policy/` | `GET` | `Bearer` | politica de snapshots |

### fallbacks-balance-cuenta

Base: `/api/finance/accounts/fallbacks-balance-cuenta/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/accounts/fallbacks-balance-cuenta/` | `GET` | `Bearer` | listar fallbacks de balance |
| `/api/finance/accounts/fallbacks-balance-cuenta/{id}/` | `GET` | `Bearer` | detalle de fallback |
| `/api/finance/accounts/fallbacks-balance-cuenta/health/` | `GET` | `Bearer` | salud agregada de fallbacks |

### outbox-cuentas

Base: `/api/finance/accounts/outbox-cuentas/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/accounts/outbox-cuentas/` | `GET` | `Bearer` | listar eventos del outbox |
| `/api/finance/accounts/outbox-cuentas/{id}/` | `GET` | `Bearer` | detalle de evento |
| `/api/finance/accounts/outbox-cuentas/{id}/publish_now/` | `POST` | `Bearer` | publicar evento ahora |
| `/api/finance/accounts/outbox-cuentas/{id}/retry/` | `POST` | `Bearer` | reintentar evento |
| `/api/finance/accounts/outbox-cuentas/{id}/release_lock/` | `POST` | `Bearer` | liberar lock |
| `/api/finance/accounts/outbox-cuentas/health/` | `GET` | `Bearer` | salud del outbox |
| `/api/finance/accounts/outbox-cuentas/contracts/` | `GET` | `Bearer` | contratos y governance del outbox |

### inteligencia y read models de cuentas

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/accounts/snapshots-portafolio-cuenta/` | `GET` | `Bearer` | listar snapshots de portafolio |
| `/api/finance/accounts/snapshots-portafolio-cuenta/{id}/` | `GET` | `Bearer` | detalle de snapshot de portafolio |
| `/api/finance/accounts/snapshots-portafolio-cuenta/refresh/` | `POST` | `Bearer` | refrescar inteligencia |
| `/api/finance/accounts/snapshots-portafolio-cuenta/overview/` | `GET` | `Bearer` | overview agregado de inteligencia |
| `/api/finance/accounts/snapshots-portafolio-cuenta/health/` | `GET` | `Bearer` | salud de inteligencia |
| `/api/finance/accounts/snapshots-portafolio-cuenta/worker-report/` | `POST` | `Internal token` | callback interno del worker |
| `/api/finance/accounts/snapshots-riesgo-cuenta/` | `GET` | `Bearer` | listar snapshots de riesgo |
| `/api/finance/accounts/snapshots-riesgo-cuenta/{id}/` | `GET` | `Bearer` | detalle de snapshot de riesgo |
| `/api/finance/accounts/senales-producto-cuenta/` | `GET` | `Bearer` | listar senales de producto |
| `/api/finance/accounts/senales-producto-cuenta/{id}/` | `GET` | `Bearer` | detalle de senal de producto |
| `/api/finance/accounts/metricas-owner-cuenta/` | `GET` | `Bearer` | listar metricas del owner |
| `/api/finance/accounts/metricas-owner-cuenta/{id}/` | `GET` | `Bearer` | detalle de metricas |
| `/api/finance/accounts/exposiciones-moneda-cuenta/` | `GET` | `Bearer` | listar exposiciones por moneda |
| `/api/finance/accounts/exposiciones-moneda-cuenta/{id}/` | `GET` | `Bearer` | detalle de exposicion |
| `/api/finance/accounts/distribuciones-tipo-cuenta/` | `GET` | `Bearer` | listar distribuciones por tipo |
| `/api/finance/accounts/distribuciones-tipo-cuenta/{id}/` | `GET` | `Bearer` | detalle de distribucion |

## Finance transactions

### transactions

Base: `/api/finance/transactions/transactions/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/transactions/transactions/` | `GET` | `Bearer` | listar ledger |
| `/api/finance/transactions/transactions/` | `POST` | `Bearer` | crear transaccion manual |
| `/api/finance/transactions/transactions/{id}/` | `GET` | `Bearer` | detalle de transaccion |
| `/api/finance/transactions/transactions/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar transaccion |
| `/api/finance/transactions/transactions/{id}/` | `DELETE` | `Bearer` | eliminar transaccion |
| `/api/finance/transactions/transactions/{id}/reasignar_cuenta/` | `POST` | `Bearer` | reasignar cuenta |
| `/api/finance/transactions/transactions/{id}/marcar_confirmada/` | `POST` | `Bearer` | marcar confirmada |
| `/api/finance/transactions/transactions/{id}/rechazar_inferida/` | `POST` | `Bearer` | rechazar borrador inferido pendiente |
| `/api/finance/transactions/transactions/{id}/add_comment/` | `POST` | `Bearer` | agregar comentario |
| `/api/finance/transactions/transactions/{id}/registrar_reembolso/` | `POST` | `Bearer` | registrar reembolso |

### inference-requests

Base: `/api/finance/transactions/inference-requests/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/transactions/inference-requests/` | `GET` | `Bearer` | listar solicitudes de inferencia transaccional visibles |
| `/api/finance/transactions/inference-requests/` | `POST` | `Bearer` | crear solicitud asincronica de voz con `X-Request-Id` e `Idempotency-Key`; solo audio/metadatos |
| `/api/finance/transactions/inference-requests/{id}/` | `GET` | `Bearer` | detalle de solicitud, estado, batch, receipts y transacciones derivadas |
| `/api/finance/transactions/inference-requests/{id}/retry/` | `POST` | `Bearer` | reintentar solicitud fallida o `dead_letter` |

### tags

Base: `/api/finance/transactions/tags/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/transactions/tags/` | `GET` | `Bearer` | listar tags |
| `/api/finance/transactions/tags/` | `POST` | `Bearer` | crear tag |
| `/api/finance/transactions/tags/{id}/` | `GET` | `Bearer` | detalle de tag |
| `/api/finance/transactions/tags/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar tag |
| `/api/finance/transactions/tags/{id}/` | `DELETE` | `Bearer` | eliminar tag |

### income-sources

Base: `/api/finance/transactions/income-sources/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/transactions/income-sources/` | `GET` | `Bearer` | listar fuentes de ingreso |
| `/api/finance/transactions/income-sources/` | `POST` | `Bearer` | crear fuente |
| `/api/finance/transactions/income-sources/{id}/` | `GET` | `Bearer` | detalle de fuente |
| `/api/finance/transactions/income-sources/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar fuente |
| `/api/finance/transactions/income-sources/{id}/` | `DELETE` | `Bearer` | eliminar fuente |

### scheduled-payments legacy

Base: `/api/finance/transactions/scheduled-payments/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/transactions/scheduled-payments/` | `GET` | `Bearer` | listar scheduled payments legacy |
| `/api/finance/transactions/scheduled-payments/` | `POST` | `Bearer` | crear scheduled payment legacy |
| `/api/finance/transactions/scheduled-payments/{id}/` | `GET` | `Bearer` | detalle |
| `/api/finance/transactions/scheduled-payments/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar |
| `/api/finance/transactions/scheduled-payments/{id}/` | `DELETE` | `Bearer` | eliminar |
| `/api/finance/transactions/scheduled-payments/{id}/generar_transaccion/` | `POST` | `Bearer` | materializar a transaccion |

### transaction-participants

Base: `/api/finance/transactions/transaction-participants/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/transactions/transaction-participants/` | `GET` | `Bearer` | listar participantes |
| `/api/finance/transactions/transaction-participants/` | `POST` | `Bearer` | crear participante |
| `/api/finance/transactions/transaction-participants/{id}/` | `GET` | `Bearer` | detalle de participante |
| `/api/finance/transactions/transaction-participants/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar participante |
| `/api/finance/transactions/transaction-participants/{id}/` | `DELETE` | `Bearer` | eliminar participante |
| `/api/finance/transactions/transaction-participants/by_contact/` | `GET` | `Bearer` | listar por contacto |
| `/api/finance/transactions/transaction-participants/summary_by_contact/` | `GET` | `Bearer` | resumen por contacto |
| `/api/finance/transactions/transaction-participants/{id}/mark_settled/` | `POST` | `Bearer` | marcar saldado |

### transactions internal intake y reconciliacion

Base: `/api/internal/transactions/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/internal/transactions/intake/batches/` | `POST` | `Internal token` | recibir lote de intake externo |
| `/api/internal/transactions/intake/batches/{batch_id}/apply/` | `POST` | `Internal token` | aplicar batch recibido |
| `/api/internal/transactions/intake/row/` | `POST` | `Internal token` | intake de una sola fila |
| `/api/internal/transactions/intake/reconcile/` | `POST` | `Internal token` | reconciliar intake externo |
| `/api/internal/transactions/reconciliation/issues/{issue_id}/resolve/` | `POST` | `Internal token` | resolver issue de reconciliacion |

### integrations llm internal worker

Base: `/api/internal/integrations/llm/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/internal/integrations/llm/transactions/inference/worker/` | `POST` | `Internal token` | worker temporal para procesar `TransactionInferenceRequest` de voz |
| `/internal/integrations/llm/transactions/inference/worker/` | `POST` | `Internal token` | prefijo legacy compatible del mismo worker |

### accounts internal sync callbacks

Base: `/api/internal/accounts/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/internal/accounts/{account_id}/sync/running/` | `POST` | `Internal token` | callback canonico de sync running |
| `/api/internal/accounts/{account_id}/sync/success/` | `POST` | `Internal token` | callback canonico de sync success |
| `/api/internal/accounts/{account_id}/sync/error/` | `POST` | `Internal token` | callback canonico de sync error |
| `/api/internal/accounts/{account_id}/sync/stale/` | `POST` | `Internal token` | callback canonico de sync stale |

## Finance auxiliares

### categories

Base: `/api/finance/categories/categorias/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/categories/categorias/` | `GET` | `Bearer` | listar categorias |
| `/api/finance/categories/categorias/` | `POST` | `Bearer` | crear categoria |
| `/api/finance/categories/categorias/{id}/` | `GET` | `Bearer` | detalle |
| `/api/finance/categories/categorias/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar |
| `/api/finance/categories/categorias/{id}/` | `DELETE` | `Bearer` | eliminar |

### debts

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/debts/deudas/` | `GET` | `Bearer` | listar deudas |
| `/api/finance/debts/deudas/` | `POST` | `Bearer` | crear deuda |
| `/api/finance/debts/deudas/{id}/` | `GET` | `Bearer` | detalle de deuda |
| `/api/finance/debts/deudas/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar deuda |
| `/api/finance/debts/deudas/{id}/` | `DELETE` | `Bearer` | eliminar deuda |
| `/api/finance/debts/cuotas-deuda/` | `GET` | `Bearer` | listar cuotas |
| `/api/finance/debts/cuotas-deuda/` | `POST` | `Bearer` | crear cuota |
| `/api/finance/debts/cuotas-deuda/{id}/` | `GET` | `Bearer` | detalle de cuota |
| `/api/finance/debts/cuotas-deuda/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar cuota |
| `/api/finance/debts/cuotas-deuda/{id}/` | `DELETE` | `Bearer` | eliminar cuota |

### fx

Base: `/api/finance/fx/tasas-fx/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/fx/tasas-fx/` | `GET` | `Bearer` | listar tasas FX |
| `/api/finance/fx/tasas-fx/` | `POST` | `Bearer` | crear tasa FX |
| `/api/finance/fx/tasas-fx/{id}/` | `GET` | `Bearer` | detalle |
| `/api/finance/fx/tasas-fx/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar |
| `/api/finance/fx/tasas-fx/{id}/` | `DELETE` | `Bearer` | eliminar |

### vendors

Base: `/api/finance/vendors/proveedores/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/finance/vendors/proveedores/` | `GET` | `Bearer` | listar proveedores |
| `/api/finance/vendors/proveedores/` | `POST` | `Bearer` | crear proveedor |
| `/api/finance/vendors/proveedores/{id}/` | `GET` | `Bearer` | detalle |
| `/api/finance/vendors/proveedores/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar |
| `/api/finance/vendors/proveedores/{id}/` | `DELETE` | `Bearer` | eliminar |

## Planning y social

### goals

Base: `/api/planning/goals/metas/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/planning/goals/metas/` | `GET` | `Bearer` | listar metas |
| `/api/planning/goals/metas/` | `POST` | `Bearer` | crear meta |
| `/api/planning/goals/metas/{id}/` | `GET` | `Bearer` | detalle |
| `/api/planning/goals/metas/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar |
| `/api/planning/goals/metas/{id}/` | `DELETE` | `Bearer` | eliminar |

### teams

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/social/teams/equipos/` | `GET` | `Bearer` | listar equipos |
| `/api/social/teams/equipos/` | `POST` | `Bearer` | crear equipo |
| `/api/social/teams/equipos/{id}/` | `GET` | `Bearer` | detalle de equipo |
| `/api/social/teams/equipos/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar equipo |
| `/api/social/teams/equipos/{id}/` | `DELETE` | `Bearer` | eliminar equipo |
| `/api/social/teams/miembros/` | `GET` | `Bearer` | listar miembros |
| `/api/social/teams/miembros/` | `POST` | `Bearer` | crear membresia de equipo |
| `/api/social/teams/miembros/{id}/` | `GET` | `Bearer` | detalle de miembro |
| `/api/social/teams/miembros/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar miembro |
| `/api/social/teams/miembros/{id}/` | `DELETE` | `Bearer` | eliminar miembro |

## Payments

### payment intents

Base: `/api/payments/intents/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/payments/intents/intents/` | `GET` | `Bearer` | listar intents |
| `/api/payments/intents/intents/` | `POST` | `Bearer` | crear payment intent |
| `/api/payments/intents/intents/{id}/` | `GET` | `Bearer` | detalle de intent |
| `/api/payments/intents/intents/pricing-preview/` | `POST` | `Bearer` | preview de pricing y fees |
| `/api/payments/intents/payouts/` | `GET` | `Bearer` | listar payout batches |
| `/api/payments/intents/payouts/` | `POST` | `Bearer` | crear payout batch |
| `/api/payments/intents/payouts/{id}/` | `GET` | `Bearer` | detalle de payout batch |
| `/api/payments/intents/outbox-pagos/` | `GET` | `Bearer` | listar outbox de pagos propio |
| `/api/payments/intents/outbox-pagos/{id}/` | `GET` | `Bearer` | detalle de evento de pagos propio |
| `/api/payments/intents/callback-receipts/` | `GET` | `Bearer` | listar receipts de callbacks propios |
| `/api/payments/intents/callback-receipts/{id}/` | `GET` | `Bearer` | detalle de receipt propio |
| `/api/payments/intents/settlements/` | `GET` | `Bearer` | listar settlements propios |
| `/api/payments/intents/settlements/{id}/` | `GET` | `Bearer` | detalle de settlement propio |
| `/api/payments/intents/operational-cases/` | `GET` | `Bearer` | listar casos operativos propios |
| `/api/payments/intents/operational-cases/{id}/` | `GET` | `Bearer` | detalle de caso operativo propio |
| `/api/payments/intents/providers/contracts/` | `GET` | `Bearer` | listar contratos de providers |
| `/api/payments/intents/providers/{provider}/contract/` | `GET` | `Bearer` | detalle de contrato por provider |
| `/api/payments/intents/provider-callback/` | `POST` | provider/internal | callback generico de provider |
| `/api/payments/intents/providers/{provider}/callback/` | `POST` | provider/internal | callback especifico |
| `/api/payments/intents/worker-report/` | `POST` | `Internal token` | ruta legacy compatible para reporte del worker |

### payments internal

Base: `/api/internal/payments/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/internal/payments/worker-report/` | `POST` | `Internal token` | ruta canonica interna para reporte del worker |

### scheduled payments modernos

Base: `/api/payments/scheduled/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/payments/scheduled/templates/` | `GET` | `Bearer` | listar templates |
| `/api/payments/scheduled/templates/` | `POST` | `Bearer` | crear template |
| `/api/payments/scheduled/templates/{id}/` | `GET` | `Bearer` | detalle de template |
| `/api/payments/scheduled/templates/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar template |
| `/api/payments/scheduled/templates/{id}/` | `DELETE` | `Bearer` | eliminar template |
| `/api/payments/scheduled/templates/{id}/request-run/` | `POST` | `Bearer` | pedir corrida programada |
| `/api/payments/scheduled/templates/from-intent/` | `POST` | `Bearer` | crear template desde intent |
| `/api/payments/scheduled/runs/` | `GET` | `Bearer` | listar corridas |
| `/api/payments/scheduled/runs/{id}/` | `GET` | `Bearer` | detalle de corrida |
| `/api/payments/scheduled/runs/{id}/materialize-intent/` | `POST` | `Bearer` | materializar intent desde corrida |

## Alerts, notifications y realtime

### alerts

Base: `/api/alerts/alertas/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/alerts/alertas/` | `GET` | `Bearer` | listar alertas |
| `/api/alerts/alertas/` | `POST` | `Bearer` | crear alerta |
| `/api/alerts/alertas/{id}/` | `GET` | `Bearer` | detalle de alerta |
| `/api/alerts/alertas/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar alerta |
| `/api/alerts/alertas/{id}/` | `DELETE` | `Bearer` | eliminar alerta |
| `/api/alerts/alertas/{id}/mark_read/` | `POST` | `Bearer` | marcar leida |
| `/api/alerts/alertas/{id}/mark_resolved/` | `POST` | `Bearer` | marcar resuelta |
| `/api/alerts/alertas/{id}/snooze/` | `POST` | `Bearer` | posponer alerta |
| `/api/alerts/internal/ai-worker/` | `POST` | `Internal token` | ruta legacy compatible del worker de IA |

### alerts internal

Base: `/api/internal/alerts/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/internal/alerts/ai-worker/` | `POST` | `Internal token` | ruta canonica interna del worker de IA |

### alert rules

Base: `/api/alerts/rules/reglas/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/alerts/rules/reglas/` | `GET` | `Bearer` | listar reglas |
| `/api/alerts/rules/reglas/` | `POST` | `Bearer` | crear regla |
| `/api/alerts/rules/reglas/{id}/` | `GET` | `Bearer` | detalle de regla |
| `/api/alerts/rules/reglas/{id}/` | `PUT`, `PATCH` | `Bearer` | actualizar regla |
| `/api/alerts/rules/reglas/{id}/` | `DELETE` | `Bearer` | eliminar regla |

### notifications.deliveries

Base: `/api/notifications/deliveries/entregas-notificacion/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/notifications/deliveries/entregas-notificacion/` | `GET` | `Bearer` | listar notificaciones |
| `/api/notifications/deliveries/entregas-notificacion/{id}/` | `GET` | `Bearer` | detalle de notificacion |
| `/api/notifications/deliveries/entregas-notificacion/{id}/mark_read/` | `POST` | `Bearer` | marcar leida |
| `/api/notifications/deliveries/entregas-notificacion/mark_all_read/` | `POST` | `Bearer` | marcar varias como leidas |
| `/api/notifications/deliveries/entregas-notificacion/stats/` | `GET` | `Bearer` | estadisticas del inbox |

### realtime.consumers

Base: `/api/realtime/consumers/senales-realtime/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/realtime/consumers/senales-realtime/` | `GET` | `Bearer` | listar senales realtime |
| `/api/realtime/consumers/senales-realtime/{id}/` | `GET` | `Bearer` | detalle de senal realtime |
| `/api/realtime/consumers/senales-realtime/latest/` | `GET` | `Bearer` | ultima senal |
| `/api/realtime/consumers/senales-realtime/stats/` | `GET` | `Bearer` | estadisticas de realtime |

## Reports y soporte

### reports

Base: `/api/reports/reportes/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/reports/reportes/cashflow` | `GET` | `Bearer` | reporte de cashflow |
| `/api/reports/reportes/gastos-por-categoria` | `GET` | `Bearer` | gastos por categoria |

### support.audit

Base: `/api/support/audit/auditoria/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/api/support/audit/auditoria/` | `GET` | `Bearer` | listar auditoria propia o global si el usuario es staff |
| `/api/support/audit/auditoria/{id}/` | `GET` | `Bearer` | detalle de evento de auditoria accesible al usuario |

## Integrations stub

Estas rutas no son el `integration_service` final. Son un puente interno del
backend actual.

Base legacy: `/internal/integrations/banks/`

| Ruta | Metodos | Auth | Uso |
|---|---|---|---|
| `/internal/integrations/banks/accounts/sync/` | `POST` | `Internal token` | disparar sync de cuentas |
| `/internal/integrations/banks/accounts/intelligence/refresh/` | `POST` | `Internal token` | refrescar inteligencia de cuentas |
| `/internal/integrations/banks/consents/revoke/` | `POST` | `Internal token` | revocar consentimiento desde integraciones |
| `/internal/integrations/banks/transactions/sync/` | `POST` | `Internal token` | enviar batch de sync transaccional |
| `/internal/integrations/banks/transactions/reconciliation/resolve/` | `POST` | `Internal token` | resolver reconciliacion transaccional |

Rutas canonicas nuevas:

- `/api/internal/integrations/banks/accounts/sync/`
- `/api/internal/integrations/banks/accounts/intelligence/refresh/`
- `/api/internal/integrations/banks/consents/revoke/`
- `/api/internal/integrations/banks/transactions/sync/`
- `/api/internal/integrations/banks/transactions/reconciliation/resolve/`

## Notas finales

- Este documento refleja las rutas visibles desde los `urls.py` y `ViewSet`
  registrados hoy en el repo.
- Cuando un router usa CRUD estandar de DRF, las rutas de `GET`, `POST`,
  `GET detail`, `PUT`, `PATCH` y `DELETE` se listan explicitamente aqui para
  facilitar pruebas manuales.
- Si se agrega, elimina o renombra un endpoint, este archivo debe actualizarse
  junto con el README del modulo dueno.
