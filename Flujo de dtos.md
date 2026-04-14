# Flujo de dtos

## Proposito

Este documento explica la estructura de datos actual de Vexxo y su ciclo de
vida operativo.

No es un inventario aislado de tablas. Su objetivo es dejar claro:

- que guarda cada capa del sistema
- quien escribe cada dato
- quien lo consume
- como se mueve la informacion entre bounded contexts
- que es fuente de verdad y que es proyeccion derivada
- que endpoints tocan cada conjunto de tablas

## Principio general

Vexxo no trata todas las tablas igual. El sistema separa:

- framework y auth base
- identidad y politica de producto
- cuentas financieras
- ledger
- pagos externos
- proyecciones, snapshots y outbox
- alertas, inbox, realtime y auditoria
- catalogos auxiliares

Tambien distingue entre:

- fuentes de verdad
- tablas derivadas o materializadas
- tablas operativas de soporte
- tablas legacy o de compatibilidad

## 1. Framework, auth y base de Django

Estas tablas no son core de negocio Vexxo, pero sostienen autenticacion,
permisos y operacion base del framework.

### Tablas

- `django_migrations`
- `django_content_type`
- `django_admin_log`
- `django_session`
- `django_site`
- `auth_group`
- `auth_permission`
- `auth_group_permissions`
- `authtoken_token`
- `token_blacklist_outstandingtoken`
- `token_blacklist_blacklistedtoken`
- `account_emailaddress`
- `account_emailconfirmation`
- `socialaccount_socialapp`
- `socialaccount_socialapp_sites`
- `socialaccount_socialaccount`
- `socialaccount_socialtoken`

### Flujo

1. el usuario se registra o inicia sesion
2. Django, allauth y JWT crean o validan identidad base
3. Vexxo aterriza eso en:
   - `users_user`
   - `identity_sessions_usersession`
   - `devices_userdevice`
   - `identity_permissions_userpermissiongrant`

## 2. Usuario, identidad y control de producto

Estas tablas definen quien es el usuario, que plan tiene y que puede hacer.

### Tablas

- `users_user`
- `devices_userdevice`
- `identity_sessions_usersession`
- `social_identities_usersocialidentity`
- `social_identities_socialauthhandoff`
- `consents_userconsent`
- `identity_permissions_userpermissiongrant`
- `identity_eventing_identitydomaineventoutbox`
- `identity_eventing_userproductusageprojection`
- `identity_eventing_userproductusageprojectionevent`

### Flujo

1. el usuario entra
2. `users_user` resuelve plan y perfil
3. `identity_permissions_userpermissiongrant` traduce plan a capabilities
4. `identity_eventing_userproductusageprojection` dice cuanto ha usado
5. guards de cuentas, reglas, IA y pagos deciden si la accion procede o no

## 3. Cuentas financieras y colaboracion

Este es el contexto `finance.accounts`. Responde: donde vive el dinero.

### Tablas

- `accounts_account`
- `accounts_accountmembership`
- `accounts_accountinvitation`
- `accounts_accountaccess`
- `accounts_balancesnapshot`
- `accounts_accountbalancefallback`
- `accounts_domaineventoutbox`
- `accounts_accountintelligencedispatchstate`
- `accounts_accountportfoliosnapshot`
- `accounts_accountrisksnapshot`
- `accounts_accountproductsignal`
- `accounts_accountownermetrics`
- `accounts_accountcurrencyexposure`
- `accounts_accounttypedistribution`

### Flujo

1. el usuario crea o conecta una cuenta
2. se crea `accounts_account`
3. si la comparte, aparecen:
   - `accounts_accountinvitation`
   - luego `accounts_accountmembership`
4. `finance.transactions` mueve el ledger
5. `accounts_account.balance` se mantiene como cache operativo
6. `accounts_balancesnapshot` y `accounts_accountbalancefallback` sirven para
   conciliacion y soporte
7. snapshots de portafolio y riesgo alimentan dashboard e inteligencia

## 4. Ledger y transacciones

Este es el nucleo contable real de Vexxo.

### Tablas

- `transactions_transaction`
- `transactions_transactionparticipant`
- `transactions_tag`
- `transactions_transaction_tags`
- `transactions_incomesource`
- `transactions_scheduledpayment`
- `transactions_scheduledpayment_tags`
- `transactions_transactiondomaineventoutbox`

### Flujo

1. el usuario registra ingreso, gasto o transferencia
2. o llega reflejo desde `payments`
3. se crea `transactions_transaction`
4. si hay contrapartes o deudas compartidas, se usan
   `transactions_transactionparticipant`
5. `accounts` actualiza balance operativo
6. `reports`, `alerts`, `contacts` y `debts` derivan efectos desde ahi

## 5. Pagos externos y dispersion

Estas tablas separan ejecucion externa de ledger.

### Tablas

- `payment_intents_paymentintent`
- `payment_intents_payoutbatch`
- `payment_intents_payoutinstruction`
- `payment_intents_paymentprovidercallbackreceipt`
- `payment_intents_paymentsettlementrecord`
- `payment_intents_paymentoperationalcase`
- `payment_intents_paymentdomaineventoutbox`
- `scheduled_payments_paymenttemplate`
- `scheduled_payments_paymentschedulerun`

### Flujo

1. el usuario quiere pagar algo externo
2. nace `payment_intents_paymentintent`
3. provider o callback actualiza estado
4. receipts, settlement y cases guardan la parte operativa
5. cuando el pago ya es contable, se crea `transactions_transaction`
6. si era recurrente, la plantilla vive en `scheduled_payments_*`, no en ledger

## 6. Alertas, notificaciones, realtime y auditoria

### Tablas

- `alerts_alert`
- `rules_rule`
- `notification_deliveries_notificationdelivery`
- `realtime_consumers_realtimesignal`
- `audit_auditlog`

### Flujo

1. ocurre un evento financiero o de producto
2. puede crearse `alerts_alert`
3. puede crearse `notification_deliveries_notificationdelivery`
4. ademas puede emitirse `realtime_consumers_realtimesignal`
5. acciones criticas quedan registradas en `audit_auditlog`

## 7. Catalogos y modulos auxiliares

### Tablas

- `categories_category`
- `vendors_vendor`
- `contacts_contact`
- `debts_debt`
- `debts_debtinstallment`
- `fx_exchangerate`
- `budgets_budget`
- `budgets_accountbudget`
- `goals_goal`
- `investments_asset`
- `investments_investmentaccount`
- `investments_position`
- `investments_pricehistory`
- `investments_trade`

### Estado real

- `categories`, `vendors`, `debts`, `contacts`, `fx`
  si tienen relacion practica con el core actual
- `budgets`, `goals`, `investments`
  existen ya en esquema, pero su explotacion funcional es menor que
  `accounts`, `transactions` y `payments`

## 8. Social y colaboracion general

### Tablas

- `teams_team`
- `teams_membership`

Modelan colaboracion general tipo equipos o grupos, separada del sharing directo
de cuentas.

## Tablas mas importantes hoy

Si se prioriza entendimiento tecnico, las tablas mas centrales hoy son:

- `users_user`
- `accounts_account`
- `accounts_accountmembership`
- `transactions_transaction`
- `transactions_transactionparticipant`
- `payment_intents_paymentintent`
- `alerts_alert`
- `notification_deliveries_notificationdelivery`
- `identity_eventing_userproductusageprojection`
- `accounts_balancesnapshot`
- `audit_auditlog`

## Flujo maestro del sistema

1. `users_user` define identidad y plan
2. `accounts_account` define donde vive el dinero
3. `transactions_transaction` define que paso contablemente
4. `payment_intents_paymentintent` ejecuta pagos externos
5. `transactions_transaction` refleja el pago confirmado
6. alertas, inbox y realtime entregan feedback
7. snapshots y proyecciones evitan recalcular todo en caliente
8. los outbox permiten publicacion confiable de eventos

## En corto: que se registra en cada capa

- identidad: quien eres y que puedes hacer
- cuentas: donde esta tu dinero y con quien compartes acceso
- ledger: que paso realmente
- pagos: que orden externa intentaste ejecutar y como respondio el rail
- proyecciones y snapshots: lecturas rapidas y operativas
- alertas, notificaciones y realtime: como se te informa
- auditoria: que hizo el sistema o el usuario
- catalogos auxiliares: clasificacion, deuda, contactos, FX, metas e inversion

## Tabla maestra de las 81 tablas

### Framework, auth y base Django

| Tabla | Modulo | Que hace | Quien la escribe | Quien la lee | Criticidad |
|---|---|---|---|---|---|
| `django_migrations` | Django | Historial de migraciones aplicadas | Django `migrate` | Django | alta |
| `django_content_type` | Django | Catalogo de modelos instalados | Django | Django/admin/permisos | media |
| `django_admin_log` | Django | Log del admin de Django | Django admin | soporte/admin | baja |
| `django_session` | Django | Sesiones server-side | Django auth/session middleware | Django | media |
| `django_site` | Django/allauth | Configuracion de sites | admin/Django | allauth | baja |
| `auth_group` | Django auth | Grupos de permisos | admin/Django | auth/admin | media |
| `auth_group_permissions` | Django auth | Relacion grupo-permiso | admin/Django | auth/admin | media |
| `auth_permission` | Django auth | Permisos nativos por modelo | Django | auth/admin | media |
| `authtoken_token` | DRF auth | Tokens DRF legacy | auth endpoints | DRF si aplica | baja |
| `token_blacklist_outstandingtoken` | JWT | Tokens JWT emitidos | simplejwt | auth/logout/refresh | alta |
| `token_blacklist_blacklistedtoken` | JWT | Tokens JWT revocados | logout/blacklist | simplejwt | alta |
| `account_emailaddress` | allauth | Emails asociados a cuenta | allauth/registro | allauth/login | media |
| `account_emailconfirmation` | allauth | Confirmaciones de email | allauth | allauth | baja |
| `socialaccount_socialapp` | allauth social | Config apps OAuth | admin | allauth | baja |
| `socialaccount_socialapp_sites` | allauth social | Relacion app OAuth-site | admin | allauth | baja |
| `socialaccount_socialaccount` | allauth social | Cuenta social enlazada | allauth | login social | media |
| `socialaccount_socialtoken` | allauth social | Tokens del proveedor social | allauth | login/refresh social | media |

### Identidad, usuario y producto

| Tabla | Modulo | Que hace | Quien la escribe | Quien la lee | Criticidad |
|---|---|---|---|---|---|
| `users_user` | `identity.users` | Usuario principal, plan, perfil, onboarding | registro/auth/admin | casi todo el sistema | alta |
| `devices_userdevice` | `identity.devices` | Dispositivos confiables/sospechosos del usuario | login/security flows | seguridad/sesiones | media |
| `identity_sessions_usersession` | `identity.sessions` | Sesiones activas del usuario | auth/login/logout | auth/security | alta |
| `consents_userconsent` | `identity.consents` | Consentimientos para integraciones y uso de datos | usuario/backend | integraciones/permissions | alta |
| `identity_permissions_userpermissiongrant` | `identity.permissions` | Entitlements/grants efectivos | identity/services | guards de producto | alta |
| `social_identities_usersocialidentity` | `identity.social_identities` | Vinculo canonico a identidades sociales | auth social | identity/auth | media |
| `social_identities_socialauthhandoff` | `identity.social_identities` | Handoff temporal del flujo social | auth social | callback social | baja |
| `identity_eventing_identitydomaineventoutbox` | `identity.eventing` | Outbox del contexto identidad | identity/services | worker/event bus | alta |
| `identity_eventing_userproductusageprojection` | `identity.eventing` | Proyeccion materializada de uso del producto | projection service/event handlers | mobile/dashboard/guards | alta |
| `identity_eventing_userproductusageprojectionevent` | `identity.eventing` | Checkpoint/idempotencia de eventos de proyeccion | projection service | projection service/ops | media |

### Cuentas y colaboracion financiera

| Tabla | Modulo | Que hace | Quien la escribe | Quien la lee | Criticidad |
|---|---|---|---|---|---|
| `accounts_account` | `finance.accounts` | Cuenta financiera operativa del usuario | accounts lifecycle/sync | accounts, transactions, payments | alta |
| `accounts_accountmembership` | `finance.accounts` | Acceso efectivo a cuentas compartidas | membership service | accounts/transactions | alta |
| `accounts_accountinvitation` | `finance.accounts` | Invitaciones a compartir cuenta | invitation service | UX/soporte/accounts | media |
| `accounts_accountaccess` | `finance.accounts` legacy | Acceso legacy/historico | migracion/backoffice | soporte legacy | baja |
| `accounts_balancesnapshot` | `finance.accounts` | Snapshot de reconciliacion balance cache vs ledger | reconcile service | soporte/observabilidad | media |
| `accounts_accountbalancefallback` | `finance.accounts` | Registro de fallback al recalcular balance | balance fallback service | soporte/ops | media |
| `accounts_domaineventoutbox` | `finance.accounts` | Outbox del dominio cuentas | accounts services | worker/event bus | alta |
| `accounts_accountintelligencedispatchstate` | `finance.accounts` | Estado de corridas de inteligencia | intelligence dispatch | intelligence/ops | media |
| `accounts_accountportfoliosnapshot` | `finance.accounts` | Snapshot agregado del portafolio | intelligence service | dashboard/intelligence | media |
| `accounts_accountrisksnapshot` | `finance.accounts` | Snapshot de riesgo | intelligence service | dashboard/intelligence | media |
| `accounts_accountproductsignal` | `finance.accounts` | Senales de producto derivadas | intelligence service | dashboard/growth | baja |
| `accounts_accountownermetrics` | `finance.accounts` | Metricas agregadas por owner | intelligence service | dashboard/ops | baja |
| `accounts_accountcurrencyexposure` | `finance.accounts` | Exposicion por moneda | intelligence service | dashboard/intelligence | baja |
| `accounts_accounttypedistribution` | `finance.accounts` | Distribucion por tipo de cuenta | intelligence service | dashboard/intelligence | baja |

### Ledger, movimientos y participantes

| Tabla | Modulo | Que hace | Quien la escribe | Quien la lee | Criticidad |
|---|---|---|---|---|---|
| `transactions_transaction` | `finance.transactions` | Hecho contable final del ledger | API, materializacion desde pagos, procesos internos | accounts, reports, alerts, debts | alta |
| `transactions_transactionparticipant` | `finance.transactions` | Participantes/contrapartes de una transaccion | transactions services/API | contacts/shared flows | media |
| `transactions_tag` | `finance.transactions` | Tags del usuario para movimientos | usuario/API | UX/reportes | baja |
| `transactions_transaction_tags` | `finance.transactions` | Relacion transaccion-tag | ORM/API | UX/reportes | baja |
| `transactions_incomesource` | `finance.transactions` | Catalogo de fuentes de ingreso | usuario/API | ledger/reportes | baja |
| `transactions_scheduledpayment` | `finance.transactions` legacy | Programacion/recordatorio local legacy | usuario/API legacy | ledger/deudas | media |
| `transactions_scheduledpayment_tags` | `finance.transactions` | Relacion scheduled payment-tag | ORM/API | UX | baja |
| `transactions_transactiondomaineventoutbox` | `finance.transactions` | Outbox del ledger | transaction signals/actions | worker/event bus | alta |

### Pagos externos y dispersion

| Tabla | Modulo | Que hace | Quien la escribe | Quien la lee | Criticidad |
|---|---|---|---|---|---|
| `payment_intents_paymentintent` | `payments.payment_intents` | Intencion y estado del pago externo | create intent, callbacks, workers | payments, transactions, UX | alta |
| `payment_intents_paymentdomaineventoutbox` | `payments.payment_intents` | Outbox fuerte de pagos | payment services | worker/event bus | alta |
| `payment_intents_paymentprovidercallbackreceipt` | `payments.payment_intents` | Recibo auditable del callback del PSP | callback service | soporte/reconciliacion | media |
| `payment_intents_paymentsettlementrecord` | `payments.payment_intents` | Settlement/conciliacion del pago | reconciliation service/workers | ops/soporte | media |
| `payment_intents_paymentoperationalcase` | `payments.payment_intents` | Casos operativos: disputa, reversal, error, refund | callbacks/ops | soporte/ops | media |
| `payment_intents_payoutbatch` | `payments.payment_intents` | Lote de dispersion | payout service | ops/UX | media |
| `payment_intents_payoutinstruction` | `payments.payment_intents` | Instruccion individual de dispersion | payout service | ops/UX | media |
| `scheduled_payments_paymenttemplate` | `payments.scheduled_payments` | Plantilla moderna de pago recurrente | scheduled payments service | scheduler/payments | media |
| `scheduled_payments_paymentschedulerun` | `payments.scheduled_payments` | Corrida concreta de la plantilla | scheduler/workers | payments/ops | media |

### Alertas, reglas, notificaciones y realtime

| Tabla | Modulo | Que hace | Quien la escribe | Quien la lee | Criticidad |
|---|---|---|---|---|---|
| `alerts_alert` | `alerts.alerts` | Alerta visible al usuario | alert services/listeners | mobile/dashboard | media |
| `rules_rule` | `alerts.rules` | Regla de automatizacion/alerta | usuario/API | alerts/rule engine | media |
| `notification_deliveries_notificationdelivery` | `notifications.deliveries` | Inbox durable del usuario | notifications listeners/services | mobile/inbox | media |
| `realtime_consumers_realtimesignal` | `realtime.consumers` | Feed tecnico liviano para polling/realtime | realtime services de domains | mobile/web | baja |
| `audit_auditlog` | `support.audit` | Auditoria funcional de acciones y decisiones | audit helpers/services | soporte/compliance | alta |

### Catalogos y modulos financieros auxiliares

| Tabla | Modulo | Que hace | Quien la escribe | Quien la lee | Criticidad |
|---|---|---|---|---|---|
| `categories_category` | `finance.categories` | Categorias del ledger | usuario/API | transactions/reports | media |
| `vendors_vendor` | `finance.vendors` | Comercios/contrapartes reutilizables | usuario/API/materializacion | transactions/payments | media |
| `contacts_contact` | `contacts` | Contactos financieros del usuario | usuario/API | participants/contacts | media |
| `debts_debt` | `finance.debts` | Deuda/obligacion financiera | usuario/API | debts, transactions | media |
| `debts_debtinstallment` | `finance.debts` | Cuotas de una deuda | usuario/API | debts, transactions | media |
| `fx_exchangerate` | `finance.fx` | Tasas de cambio | jobs/API | accounts/reports | baja |
| `budgets_budget` | `finance.budgets` | Presupuesto | budgets service/API | budgets/reporting | baja |
| `budgets_accountbudget` | `finance.budgets` | Relacion presupuesto-cuenta | budgets service/API | budgets | baja |
| `goals_goal` | `planning.goals` | Meta financiera | goals service/API | planning/dashboard | baja |
| `investments_asset` | `finance.investments` | Activo financiero | investments service | investments | baja |
| `investments_investmentaccount` | `finance.investments` | Cuenta de inversion | investments service | investments | baja |
| `investments_position` | `finance.investments` | Posicion en activo | investments service | investments/dashboard | baja |
| `investments_pricehistory` | `finance.investments` | Historico de precios | jobs/integrations | investments | baja |
| `investments_trade` | `finance.investments` | Operacion de compra/venta | investments service | investments | baja |

### Social y permisos Django sobre el modelo custom

| Tabla | Modulo | Que hace | Quien la escribe | Quien la lee | Criticidad |
|---|---|---|---|---|---|
| `teams_team` | `social.teams` | Equipo/grupo social | social service/API | social UX | baja |
| `teams_membership` | `social.teams` | Membresia dentro del equipo | social service/API | social UX | baja |
| `users_user_groups` | Django + `users` | Relacion usuario-grupo | Django/admin | auth/admin | baja |
| `users_user_user_permissions` | Django + `users` | Permisos directos del usuario | Django/admin | auth/admin | baja |

## Matriz de dependencia de datos

### Identidad y producto

| Origen | Evento / proceso | Derivada | La consume |
|---|---|---|---|
| `users_user` | `users.registered.v1` | `accounts_account` | `/api/finance/accounts/cuentas/`, dashboard |
| `users_user` | `users.registered.v1` | `identity_eventing_userproductusageprojection` | `/api/identity/users/me/`, `/api/identity/users/dashboard/` |
| `users_user` | `users.onboarding.completed.v1` | `alerts_alert` | `/api/alerts/alertas/` |
| `users_user` | `users.plan.changed.v1` | refresh de `accounts_*snapshot`, `accounts_*metrics` | dashboard de usuario |
| `users_user` | `users.currency.changed.v1` | actualizacion de `accounts_account.base_currency` | cuentas, dashboard |
| `consents_userconsent` / `identity_permissions_userpermissiongrant` | revocacion de permiso/consent | cambios en `accounts_account` conectadas, sync deshabilitado | cuentas, sync interno |
| `accounts.*`, `payments.*`, `alerts.ai.enriched.*` | listeners de proyeccion | `identity_eventing_userproductusageprojection` | guards de plan, `/me`, dashboard |
| eventos aplicados a usage projection | dedupe/checkpoint | `identity_eventing_userproductusageprojectionevent` | servicio de proyeccion, soporte |

### Cuentas

| Origen | Evento / proceso | Derivada | La consume |
|---|---|---|---|
| `accounts_account` | create/update/archive/primary/sync | `accounts_domaineventoutbox` | worker `accounts_publish_outbox`, bus |
| `accounts_account` | refresh de inteligencia | `accounts_accountportfoliosnapshot` | dashboard, intelligence views |
| `accounts_account` | refresh de inteligencia | `accounts_accountrisksnapshot` | dashboard, intelligence views |
| `accounts_account` | refresh de inteligencia | `accounts_accountproductsignal` | dashboard/producto |
| `accounts_account` | refresh de inteligencia | `accounts_accountownermetrics` | dashboard/ops |
| `accounts_account` | refresh de inteligencia | `accounts_accountcurrencyexposure` | dashboard |
| `accounts_account` | refresh de inteligencia | `accounts_accounttypedistribution` | dashboard |
| `accounts_account` | dispatch de refresh | `accounts_accountintelligencedispatchstate` | support/intelligence status |
| `accounts_accountmembership` | invited/accepted/revoked | `notification_deliveries_notificationdelivery` | inbox `/api/notifications/deliveries/` |
| `accounts_accountmembership` | create/update/revoke | delta en `identity_eventing_userproductusageprojection` | guards/capabilities |
| `transactions_transaction` | signal de balance incremental | `accounts_account.balance` | cuentas, dashboard |
| `transactions_transaction` | fallback de balance | `accounts_accountbalancefallback` | `/api/finance/accounts/fallbacks-balance-cuenta/` |
| `transactions_transaction` | reconciliacion | `accounts_balancesnapshot` | `/api/finance/accounts/snapshots-balance/` |
| `accounts.balance.updated.v1` | realtime service | `realtime_consumers_realtimesignal` | `/api/realtime/consumers/...` |
| `accounts.primary.changed.v1`, `accounts.archived.v1`, `accounts.sync.succeeded.v1` | realtime service | `realtime_consumers_realtimesignal` | mobile/web polling |
| `accounts.sync.scheduled.v1` | listener | Cloud Task / integrations stub, no tabla derivada directa | worker interno |
| `accounts.membership.*`, `accounts.primary.changed`, `accounts.archived`, `accounts.sync.succeeded` | notifications listener | `notification_deliveries_notificationdelivery` | inbox |

### Ledger y transacciones

| Origen | Evento / proceso | Derivada | La consume |
|---|---|---|---|
| `transactions_transaction` | create/update/delete/confirm | `transactions_transactiondomaineventoutbox` | worker `transactions_publish_outbox` |
| `transactions_transaction` | contabilidad real | `accounts_account.balance` | cuentas |
| `transactions_transaction` | create/confirm/financial update | `debts_debt`, `debts_debtinstallment` reconciliados | modulo de deudas |
| `transactions_transaction` | over-limit check | `alerts_alert` | alertas |
| `transactions_transactionparticipant` | create/update/delete/settled | `contacts_contact.net_balance` recalculado | contactos |
| `transactions_scheduledpayment` | create/update/delete/paid | refresh slice de usage | `identity_eventing_userproductusageprojection` |
| `transactions_transaction` | agregacion simple | vistas de `reports` | `/api/reports/reportes/...` |

### Pagos externos

| Origen | Evento / proceso | Derivada | La consume |
|---|---|---|---|
| `payment_intents_paymentintent` | create/update status | `payment_intents_paymentdomaineventoutbox` | worker `payments_publish_outbox` |
| `payment_intents_paymentintent` | callback PSP | `payment_intents_paymentprovidercallbackreceipt` | soporte/ops |
| `payment_intents_paymentintent` | settlement/reconciliacion | `payment_intents_paymentsettlementrecord` | soporte/ops |
| `payment_intents_paymentintent` | error/dispute/reversal | `payment_intents_paymentoperationalcase` | soporte/ops |
| `payment_intents_paymentintent` `succeeded/settled` | materializacion contable | `transactions_transaction` | ledger, accounts, reports |
| `payment_intents_paymentintent` | eventos `payments.intent.*` | delta de pagos en `identity_eventing_userproductusageprojection` | plan/usage |
| `payment_intents_payoutbatch` / `payment_intents_payoutinstruction` | `payments.payout.*` | delta de payouts en `identity_eventing_userproductusageprojection` | plan/usage |
| `payments.intent.*`, `payments.payout.*` | realtime payment service | `realtime_consumers_realtimesignal` | mobile/web |
| `scheduled_payments_paymenttemplate` | corrida programada | `scheduled_payments_paymentschedulerun` | scheduling/payments |
| `scheduled_payments_paymentschedulerun` | ejecucion futura | `payment_intents_paymentintent` | payments |

## Matriz por endpoint

### Identity

| Endpoint | Que toca | Tablas principales | Evento / side effects | Que termina consumiendolo |
|---|---|---|---|---|
| `POST /api/identity/users/auth/register/` | crea usuario | `users_user`, tablas allauth/social si aplica | `users.registered.v1`; bootstrap de cuenta financiera; refresh de usage projection | `accounts_account`, `identity_eventing_userproductusageprojection`, alertas de bienvenida |
| `POST /api/identity/users/auth/login/` | autentica usuario | `users_user`, `identity_sessions_usersession`, `devices_userdevice`, JWT blacklist/outstanding | registra sesion/dispositivo | auth, seguridad, mobile |
| `POST /api/identity/users/auth/refresh/` | refresca JWT | `token_blacklist_outstandingtoken` | rotacion/blacklist si aplica | auth |
| `POST /api/identity/users/auth/logout/` | invalida sesion/token | `identity_sessions_usersession`, `token_blacklist_blacklistedtoken` | revocacion de sesion/token | auth |
| `GET /api/identity/users/me/` | perfil + capabilities + usage | `users_user`, `identity_permissions_userpermissiongrant`, `identity_eventing_userproductusageprojection` | lectura pura | mobile/web |
| `POST /api/identity/users/onboarding/complete/` | completa onboarding | `users_user` | `users.onboarding.completed.v1`; crea alertas de bienvenida | `alerts_alert` |
| `GET /api/identity/users/dashboard/` | dashboard de usuario | `users_user`, `identity_eventing_userproductusageprojection`, `accounts_accountportfoliosnapshot`, `accounts_accountrisksnapshot` | lectura de proyecciones | dashboard mobile/web |

### Accounts

| Endpoint | Que toca | Tablas principales | Evento / side effects | Que termina consumiendolo |
|---|---|---|---|---|
| `GET /api/finance/accounts/cuentas/` | lista cuentas visibles | `accounts_account`, `accounts_accountmembership` | lectura pura | mobile/web |
| `POST /api/finance/accounts/cuentas/` | crea cuenta | `accounts_account`, `accounts_accountmembership`, `accounts_domaineventoutbox` | `accounts.created.v1` | realtime, notifications, intelligence, usage projection |
| `PATCH /api/finance/accounts/cuentas/{id}/` | actualiza cuenta | `accounts_account`, `accounts_domaineventoutbox` | `accounts.updated.v1` | intelligence, usage projection |
| `POST /api/finance/accounts/cuentas/{id}/set_primary/` | cambia cuenta principal | `accounts_account`, `accounts_domaineventoutbox` | `accounts.primary.changed.v1`; notificacion; realtime | inbox, realtime, dashboard |
| `POST /api/finance/accounts/cuentas/{id}/archive/` | archiva cuenta | `accounts_account`, `accounts_domaineventoutbox` | `accounts.archived.v1`; notificacion; realtime | inbox, realtime |
| `POST /api/finance/accounts/cuentas/{id}/link_external_source/` | vincula cuenta externa | `accounts_account`, `accounts_domaineventoutbox` | `accounts.external.linked.v1` | usage projection, sync/intelligence |
| `POST /api/finance/accounts/cuentas/{id}/schedule_sync/` | agenda sync | `accounts_account`, `accounts_domaineventoutbox` | `accounts.sync.scheduled.v1` | worker interno / integraciones |

### Transactions

| Endpoint | Que toca | Tablas principales | Evento / side effects | Que termina consumiendolo |
|---|---|---|---|---|
| `GET /api/finance/transactions/transactions/` | lista ledger | `transactions_transaction`, `accounts_accountmembership` | lectura | mobile/web/reports |
| `POST /api/finance/transactions/transactions/` | crea transaccion | `transactions_transaction`, `transactions_transactiondomaineventoutbox` | `transactions.created.v1`; accounts balance; debts; alerts; contacts | accounts, debts, alerts, contacts |
| `PATCH /api/finance/transactions/transactions/{id}/` | actualiza transaccion | `transactions_transaction`, `transactions_transactiondomaineventoutbox` | `transactions.updated.v1` o `transactions.financial.updated.v1` | accounts, debts, alerts |
| `POST /api/finance/transactions/transactions/{id}/marcar_confirmada/` | confirma movimiento | `transactions_transaction`, `transactions_transactiondomaineventoutbox` | `transactions.confirmed.v1` | accounts, debts, alerts |
| `POST /api/finance/transactions/transactions/{id}/registrar_reembolso/` | registra reembolso | `transactions_transaction`, `transactions_transactiondomaineventoutbox` | `transactions.reimbursement.recorded.v1` | ledger, accounts, reports |
| `POST /api/finance/transactions/scheduled-payments/{id}/generar_transaccion/` | materializa scheduled legacy | `transactions_scheduledpayment`, `transactions_transaction` | `transactions.scheduled_payment.paid.v1` + evento de transaccion | ledger, accounts, usage |

### Payments

| Endpoint | Que toca | Tablas principales | Evento / side effects | Que termina consumiendolo |
|---|---|---|---|---|
| `GET /api/payments/intents/intents/` | lista intents | `payment_intents_paymentintent` | lectura | mobile/web |
| `POST /api/payments/intents/intents/` | crea intento de pago | `payment_intents_paymentintent`, `payment_intents_paymentdomaineventoutbox` | `payments.order.requested.v1`, `payments.fee.calculated.v1`, `payments.intent.created.v1` | worker PSP, usage, realtime |
| `POST /api/payments/intents/intents/pricing-preview/` | calcula fee | sin persistencia principal | calculo centralizado | mobile |
| `POST /api/payments/intents/payouts/` | crea batch de dispersion | `payment_intents_payoutbatch`, `payment_intents_payoutinstruction`, outbox | `payments.payout.requested.v1` | worker, usage, realtime |
| `POST /api/payments/intents/provider-callback/` | callback PSP | `payment_intents_paymentprovidercallbackreceipt`, `payment_intents_paymentintent`, `payment_intents_paymentsettlementrecord`, `payment_intents_paymentoperationalcase` | cambia estado `payments.intent.*`; puede materializar ledger | transactions, usage, realtime, ops |
| `POST /api/payments/intents/worker-report/` | worker report interno | `payment_intents_paymentintent` y tablas operativas | `payments.intent.dispatched/processing/requires_action/succeeded/failed/...` | realtime, usage, ledger |

### Alerts, notifications y realtime

| Endpoint | Que toca | Tablas principales | Evento / side effects | Que termina consumiendolo |
|---|---|---|---|---|
| `GET /api/alerts/alertas/` | lista alertas | `alerts_alert` | lectura | mobile/web |
| `POST /api/alerts/internal/ai-worker/` | enriquece alerta con IA | `alerts_alert` | `alerts.ai.enriched.v1` | usage projection, UI |
| `GET /api/notifications/deliveries/` | lista inbox | `notification_deliveries_notificationdelivery` | lectura | mobile/web |
| `POST /api/notifications/deliveries/{id}/mark_read/` | marca item leido | `notification_deliveries_notificationdelivery` | cambio de estado | inbox |
| `GET /api/realtime/consumers/senales-realtime/` | feed tecnico | `realtime_consumers_realtimesignal` | lectura | mobile/web polling |

## Mapa corto de side effects mas importantes

### Cuando creas una transaccion

- toca `transactions_transaction`
- genera `transactions_transactiondomaineventoutbox`
- `accounts` actualiza balance cacheado
- `debts` puede aplicar pago
- `alerts` puede crear alerta por sobrelimite
- `contacts` puede recalcular net balance por participantes

### Cuando creas un payment intent

- toca `payment_intents_paymentintent`
- genera outbox de pagos
- `identity_eventing_userproductusageprojection` puede sumar uso
- `realtime_consumers_realtimesignal` puede mostrar estado UX
- cuando el PSP confirma, termina creando `transactions_transaction`

### Cuando compartes una cuenta

- toca `accounts_accountinvitation` y/o `accounts_accountmembership`
- genera `accounts.membership.*`
- `notification_deliveries_notificationdelivery` avisa
- `identity_eventing_userproductusageprojection` ajusta uso/colaboracion

### Cuando entra un callback PSP

- toca `payment_intents_paymentprovidercallbackreceipt`
- actualiza `payment_intents_paymentintent`
- puede escribir `payment_intents_paymentsettlementrecord`
- puede abrir `payment_intents_paymentoperationalcase`
- puede materializar `transactions_transaction`

## Flujos end-to-end clave

### Registro de usuario

1. `POST /api/identity/users/auth/register/`
2. se crea `users_user`
3. se emite `users.registered.v1`
4. `finance.accounts` crea `accounts_account`
5. `identity_eventing_userproductusageprojection` se inicializa o refresca
6. si aplica, se crean alertas de onboarding

### Gasto manual

1. `POST /api/finance/transactions/transactions/`
2. se crea `transactions_transaction`
3. se encola `transactions_transactiondomaineventoutbox`
4. `accounts` actualiza `accounts_account.balance`
5. si aplica:
   - `debts` reconcilia pago
   - `alerts` crea `alerts_alert`
   - `contacts` recalcula balance neto

### Pago externo confirmado

1. `POST /api/payments/intents/intents/`
2. se crea `payment_intents_paymentintent`
3. se encola `payment_intents_paymentdomaineventoutbox`
4. worker o PSP ejecuta el rail
5. entra callback:
   - `payment_intents_paymentprovidercallbackreceipt`
   - `payment_intents_paymentintent` cambia de estado
   - opcionalmente `payment_intents_paymentsettlementrecord`
   - opcionalmente `payment_intents_paymentoperationalcase`
6. cuando el pago ya es contable:
   - se crea `transactions_transaction`
   - `accounts` actualiza balance
   - `identity_eventing_userproductusageprojection` ajusta uso
   - `realtime_consumers_realtimesignal` informa a la UI

## Fuentes principales vs derivadas

### Fuentes principales

- `users_user`
- `accounts_account`
- `accounts_accountmembership`
- `transactions_transaction`
- `transactions_transactionparticipant`
- `payment_intents_paymentintent`
- `scheduled_payments_paymenttemplate`

### Derivadas o materializadas

- `identity_eventing_userproductusageprojection`
- `identity_eventing_userproductusageprojectionevent`
- `accounts_balancesnapshot`
- `accounts_accountbalancefallback`
- `accounts_accountportfoliosnapshot`
- `accounts_accountrisksnapshot`
- `accounts_accountproductsignal`
- `accounts_accountownermetrics`
- `accounts_accountcurrencyexposure`
- `accounts_accounttypedistribution`
- `accounts_accountintelligencedispatchstate`
- `payment_intents_paymentprovidercallbackreceipt`
- `payment_intents_paymentsettlementrecord`
- `payment_intents_paymentoperationalcase`
- `notification_deliveries_notificationdelivery`
- `realtime_consumers_realtimesignal`
- `audit_auditlog`

## Uso recomendado de este documento

Sirve para:

- onboarding tecnico
- entendimiento de base de datos
- debugging de side effects
- auditoria funcional
- mapeo de datos antes de mover cosas a BigQuery, Dataflow o nuevos servicios

No reemplaza los README de cada modulo. Los complementa desde la perspectiva del
flujo de datos y ciclo de vida del dato dentro de Vexxo.

## Auditoria del flujo de datos

Esta auditoria resume el estado actual del backend segun el codigo y los
contratos hoy presentes.

## Lo que esta bien resuelto

### 1. Separacion clara entre fuente y derivada

El sistema ya distingue razonablemente bien entre:

- fuente principal:
  - `users_user`
  - `accounts_account`
  - `transactions_transaction`
  - `payment_intents_paymentintent`
- derivadas/materializadas:
  - `identity_eventing_userproductusageprojection`
  - snapshots de `accounts`
  - `notification_deliveries_notificationdelivery`
  - `realtime_consumers_realtimesignal`

Eso evita mezclar UX, soporte y verdad contable en una sola tabla.

### 2. Separacion correcta entre pagos y ledger

Hoy ya esta bien modelado que:

- `payments.payment_intents` ejecuta afuera
- `finance.transactions` refleja adentro

Eso protege el ledger y evita que la semantica del PSP contamine la verdad
contable.

### 3. Outbox fuerte en contextos importantes

El flujo de datos ya tiene outbox fuerte en:

- `identity`
- `accounts`
- `transactions`
- `payments`

Eso mejora:

- trazabilidad
- retry
- consistencia entre cambio local y publicacion
- posibilidad de mover consumidores a GCP sin redisenar la persistencia base

### 4. Proyecciones y snapshots bien orientados a mobile

La existencia de:

- `identity_eventing_userproductusageprojection`
- `accounts_balancesnapshot`
- `accounts_accountportfoliosnapshot`
- `accounts_accountrisksnapshot`

es correcta para no recalcular todo desde OLTP en cada request.

## Lo que falta o sigue incompleto

### 1. `identity_eventing_userproductusageprojection` sigue siendo hibrida

Aunque ya salio del request path, la proyeccion de uso no es 100% incremental
en todos los frentes.

Hoy mezcla:

- delta exacto en varias rutas
- sync por slice en otras
- rebuild completo como fallback

Eso esta bien para esta fase, pero todavia implica acoplamiento del proyector a
consultas OLTP en algunos caminos.

### 2. Reporting sigue siendo sobre lectura agregada y no sobre tablas propias

`reports.reports` hoy consume `transactions_transaction` directamente para
cashflow y gastos por categoria.

Eso sirve ahora, pero significa que:

- el reporting pesado todavia no esta separado
- no hay snapshots/materializaciones de reportes para consumo frecuente
- si el uso crece, esta parte deberia migrar a snapshots propios o analitica
  externa

### 3. Notificaciones todavia dependen sobre todo de `accounts.*`

La infraestructura de inbox durable existe, pero el set de listeners visibles
hoy esta mas maduro para eventos de cuentas que para el resto del negocio.

Eso significa que:

- el inbox ya existe
- pero la cobertura funcional del flujo de notificaciones todavia no es tan
  amplia como la del event bus general

### 4. Coexisten dos mundos de pagos programados

Hoy conviven:

- `transactions_scheduledpayment`
  - legacy/local/manual
- `scheduled_payments_paymenttemplate`
  - capa nueva moderna

La convivencia esta documentada y es intencional, pero sigue siendo una
frontera a consolidar a mediano plazo.

### 5. Falta una salida analitica explicita fuera de Cloud SQL

El modelo ya esta preparado para GCP, pero en el flujo de datos actual del repo
todavia no hay una bajada materializada visible hacia:

- BigQuery
- Dataflow
- CDC formal

La arquitectura lo prevé, pero el flujo de datos en codigo todavia es
principalmente OLTP + outbox + proyecciones locales.

## Riesgos actuales

### 1. Riesgo de crecimiento de tablas operativas

Tablas como:

- `realtime_consumers_realtimesignal`
- `notification_deliveries_notificationdelivery`
- `accounts_balancesnapshot`
- `accounts_accountbalancefallback`
- tablas de receipts/cases de pagos

pueden crecer bastante.

Eso exige gobernanza de:

- indices
- paginacion
- retention/cleanup
- separacion entre UX operativa y analitica historica

### 2. Riesgo de duplicacion de efectos si el contrato del evento se degrada

La base de idempotencia existe, pero depende de que:

- `idempotency_key`
- `projection_event_key`
- `outbox_event_id`
- `correlation_id`

se sigan propagando bien.

Si nuevos flujos empiezan a emitir eventos sin esa disciplina, el riesgo sube
en:

- projections
- payouts
- inbox
- side effects de ledger

### 3. Riesgo de reporting y dashboards sobre OLTP caliente

Hoy los reportes visibles son todavia ligeros. Si el producto empieza a pedir:

- historicos largos
- comparativas
- cohortes
- analitica cross-tenant

no deberia salir de Cloud SQL request-path.

## Mejoras priorizadas

### Prioridad alta

- terminar de llevar `identity_eventing_userproductusageprojection` a una
  proyeccion incremental pura donde sea posible
- ampliar listeners canónicos hacia `notification_deliveries` para mas eventos
  de pagos, transacciones y lifecycle del usuario
- definir una politica explicita de retention para:
  - realtime
  - inbox
  - snapshots
  - receipts/cases de pagos

### Prioridad media

- materializar snapshots o read models propios para reporting frecuente
- consolidar la historia de scheduled payments entre legacy y modulo nuevo
- agregar mas visibilidad de causalidad entre evento emitido y proyeccion
  afectada

### Prioridad futura

- exportar eventos o snapshots clave hacia BigQuery
- separar reporting pesado de OLTP
- construir pipelines analiticos sobre eventos y snapshots en vez de consultas
  ad hoc al monolito

## Conclusiones operativas

### Conclusion 1

El flujo de datos actual ya tiene una estructura seria y escalable:

- fuente de verdad clara
- outbox fuerte
- proyecciones materializadas
- separacion entre rail externo y ledger

### Conclusion 2

La mayor deuda no esta en el modelo central, sino en:

- completar proyecciones incrementales
- ampliar cobertura de notificaciones derivadas
- sacar reporting pesado de OLTP
- gobernar crecimiento de tablas operativas

### Conclusion 3

Si hoy hubiera que endurecer solo una cosa mas en datos, la prioridad tecnica
mas valiosa seria:

1. consolidar proyecciones/materializaciones
2. definir retention y observabilidad de feeds operativos
3. preparar salida analitica a GCP sin cargar Cloud SQL



## Addendum 2026-04 Integraciones Y Contratos Canonicos

Este documento debe leerse ahora con estas reglas adicionales:

- `bank_data` entra por `finance.accounts` y `finance.transactions`
- `payment_execution` vive en `payments.payment_intents`
- `payment_reflection` vive en `finance.transactions`
- `market_data` vive en `finance.fx`
- `message_inferred` entra por el parser interno de `transactions`

Flujos relevantes incorporados en la arquitectura actual:

1. `Belvo` / `Salt Edge` / agregador bancario
   - bridge o integrador normaliza
   - entra por intake de `transactions`
   - materializa `Transaction`, `TransactionExternalDetails` y `TransactionSourceLink`

2. `Wompi` o PSP
   - callback y lifecycle operativo viven primero en `payments`
   - cuando el movimiento ya vale para ledger, se genera `payment_reflection`
   - solo entonces se materializa `Transaction`

3. `SMS/email`
   - entra por `POST /api/internal/transactions/intake/message/`
   - parser determinista infiere monto/tipo/descripcion
   - se persiste `Transaction` en `pending + confirmed=false`
   - `TransactionExternalDetails` conserva metadata de inferencia

4. `FX / tasas`
   - no deben tocar `transactions`
   - se persisten como snapshots en `finance.fx`

Documentos canonicos relacionados:

- [INTEGRATION_SOURCE_CATALOG.md](/D:/Vexxo_Backend_API/INTEGRATION_SOURCE_CATALOG.md)
- [RAIL_NORMALIZATION_CONTRACTS.md](/D:/Vexxo_Backend_API/finance/transactions/RAIL_NORMALIZATION_CONTRACTS.md)
- [PAYMENT_EXECUTION_CONTRACTS.md](/D:/Vexxo_Backend_API/payments/payment_intents/PAYMENT_EXECUTION_CONTRACTS.md)

