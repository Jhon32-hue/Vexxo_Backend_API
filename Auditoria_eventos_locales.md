# Auditoria de eventos locales

## Objetivo

Este documento audita el consumo local de eventos en Vexxo para cuatro
bounded contexts:

- `accounts`
- `transactions`
- `payments`
- `identity`

El foco no es Pub/Sub cloud. El foco es:

- que evento se publica
- que listener local lo consume
- que side effect interno produce
- que efecto visible termina generando

## Regla actual de ejecucion local

En cloud, la arquitectura sigue siendo:

1. request persiste cambio
2. request deja evento en outbox
3. worker publica
4. listeners locales y dispatchers externos reaccionan

En local, ahora existe una ayuda extra:

- `DOMAIN_EVENTS_LOCAL_AUTOPUBLISH_ENABLED=true`

Con esa bandera:

- el request sigue persistiendo primero en outbox
- despues del commit el evento se autopublica al bus local
- los listeners locales pueden reaccionar sin correr workers aparte

Esto no elimina:

- outbox
- management commands `*_publish_outbox`
- Pub/Sub
- configuracion cloud

Solo hace mas facil probar side effects end-to-end en desarrollo.

## Hallazgo principal

La razon por la que antes parecia que "crear cuenta no dispara nada" era esta:

- `accounts`, `transactions`, `payments` e `identity` usan outbox
- el request web no publica inline
- sin worker local, los listeners no veian el evento

Ahora, en local, eso puede resolverse con autopublicacion after-commit.

## 1. Accounts

### Resumen

`accounts` si tiene consumidores locales, pero no todos producen un efecto
visible inmediato para el usuario.

El patron actual es:

- muchos `accounts.*` refrescan inteligencia y usage projection
- solo algunos terminan en `realtime`, `notifications` o `alerts`

### Matriz exacta

| Evento | Listener local | Side effect interno | Efecto visible |
|---|---|---|---|
| `accounts.created.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia por owner | indirecto en dashboard cuando se lean snapshots |
| `accounts.created.v1` | `users.refresh_usage_projection_from_accounts` | delta/refresco de `UserProductUsageProjection` | visible en `/api/identity/users/me/` y `/api/identity/users/dashboard/` |
| `accounts.updated.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto en dashboard |
| `accounts.updated.v1` | `users.refresh_usage_projection_from_accounts` | refresco de usage projection | visible en identidad si cambia el conteo/capacidad |
| `accounts.closed.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto |
| `accounts.closed.v1` | `users.refresh_usage_projection_from_accounts` | delta de usage projection | visible en identidad |
| `accounts.frozen.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto |
| `accounts.frozen.v1` | `users.refresh_usage_projection_from_accounts` | delta de usage projection | visible en identidad |
| `accounts.unfrozen.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto |
| `accounts.unfrozen.v1` | `users.refresh_usage_projection_from_accounts` | delta de usage projection | visible en identidad |
| `accounts.archived.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto en dashboard |
| `accounts.archived.v1` | `accounts.publish_archived_realtime_signal` | crea `RealtimeSignal` | visible en `/api/realtime/consumers/senales-realtime/` |
| `accounts.archived.v1` | `users.refresh_usage_projection_from_accounts` | delta de usage projection | visible en identidad |
| `accounts.archived.v1` | `notifications.handle_account_archived` | crea `NotificationDelivery` | visible en `/api/notifications/deliveries/entregas-notificacion/` |
| `accounts.unarchived.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto |
| `accounts.unarchived.v1` | `users.refresh_usage_projection_from_accounts` | delta de usage projection | visible en identidad |
| `accounts.recalculated.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto |
| `accounts.recalculated.v1` | `users.refresh_usage_projection_from_accounts` | refresco de usage projection | visible en identidad si cambia capacidad/uso |
| `accounts.balance.updated.v1` | `accounts.publish_balance_updated_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `accounts.balance.updated.v1` | `alerts.handle_account_balance_updated` | evalua alertas por cambio de balance | puede crear `Alert` visible en `/api/alerts/alertas/` |
| `accounts.balance.snapshot.created.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto |
| `accounts.balance.snapshot.created.v1` | `users.refresh_usage_projection_from_accounts` | refresco de usage projection | normalmente no visible directo |
| `accounts.balance.drift.detected.v1` | `accounts.log_account_drift_detected` | log warning | no visible al usuario |
| `accounts.balance.drift.detected.v1` | `alerts.handle_account_drift_detected` | crea alerta critica de sistema | visible en alertas |
| `accounts.external.linked.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto |
| `accounts.external.linked.v1` | `users.refresh_usage_projection_from_accounts` | suma/delta de cuentas conectadas | visible en identidad |
| `accounts.external.unlinked.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto |
| `accounts.external.unlinked.v1` | `users.refresh_usage_projection_from_accounts` | resta/delta de cuentas conectadas | visible en identidad |
| `accounts.sync.scheduled.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto |
| `accounts.sync.scheduled.v1` | `accounts.enqueue_scheduled_sync_task` | crea Cloud Task o camino equivalente | no visible directo |
| `accounts.sync.status.changed.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto |
| `accounts.sync.status.changed.v1` | `users.refresh_usage_projection_from_accounts` | refresco de projection | no visible directo normalmente |
| `accounts.sync.started.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto |
| `accounts.sync.started.v1` | `users.refresh_usage_projection_from_accounts` | refresco de projection | no visible directo normalmente |
| `accounts.sync.succeeded.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto en dashboard |
| `accounts.sync.succeeded.v1` | `accounts.publish_sync_succeeded_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `accounts.sync.succeeded.v1` | `notifications.handle_account_sync_succeeded` | crea `NotificationDelivery` | visible en inbox |
| `accounts.sync.succeeded.v1` | `users.refresh_usage_projection_from_accounts` | refresco de projection | visible en identidad si afecta conteos |
| `accounts.sync.failed.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto |
| `accounts.sync.failed.v1` | `alerts.handle_account_sync_failed` | crea alerta de sistema | visible en alertas |
| `accounts.sync.failed.v1` | `users.refresh_usage_projection_from_accounts` | refresco de projection | normalmente no visible directo |
| `accounts.primary.changed.v1` | `accounts.refresh_owner_account_intelligence` | agenda refresh de inteligencia | indirecto en dashboard |
| `accounts.primary.changed.v1` | `accounts.publish_primary_changed_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `accounts.primary.changed.v1` | `notifications.handle_account_primary_changed` | crea `NotificationDelivery` | visible en inbox |
| `accounts.primary.changed.v1` | `users.refresh_usage_projection_from_accounts` | refresco de projection | no visible directo normalmente |
| `accounts.membership.created.v1` | `users.refresh_usage_projection_from_accounts` | delta de membresias compartidas | visible en identidad |
| `accounts.membership.invited.v1` | `users.refresh_usage_projection_from_accounts` | delta de membresias compartidas | visible en identidad |
| `accounts.membership.invited.v1` | `notifications.handle_account_membership_invited` | crea `NotificationDelivery` | visible en inbox |
| `accounts.membership.updated.v1` | `users.refresh_usage_projection_from_accounts` | delta de membresias compartidas | visible en identidad |
| `accounts.membership.accepted.v1` | `users.refresh_usage_projection_from_accounts` | delta de membresias compartidas | visible en identidad |
| `accounts.membership.accepted.v1` | `notifications.handle_account_membership_accepted` | crea `NotificationDelivery` | visible en inbox |
| `accounts.membership.revoked.v1` | `users.refresh_usage_projection_from_accounts` | delta de membresias compartidas | visible en identidad |
| `accounts.membership.revoked.v1` | `notifications.handle_account_membership_revoked` | crea `NotificationDelivery` | visible en inbox |

### Conclusion de accounts

`accounts.created.v1` si se consume localmente, pero hoy sus efectos son
principalmente:

- refresh de inteligencia
- usage projection

No genera por si solo:

- notificacion
- alerta
- realtime visible

Por eso al crear una cuenta nueva el usuario puede no ver una reaccion obvia,
aunque el evento si haya sido consumido.

## 2. Transactions

### Resumen

`transactions` si tiene consumo local, pero esta mas orientado a efectos de
negocio interno que a UX directa.

### Matriz exacta

| Evento | Listener local | Side effect interno | Efecto visible |
|---|---|---|---|
| `transactions.created.v1` | `transactions.handle_transaction_side_effects` | aplica pago a deuda si corresponde | visible indirectamente en estado de deuda |
| `transactions.created.v1` | `transactions.handle_transaction_side_effects` | marca `ScheduledPayment` legacy como pagado si aplica | visible indirectamente en scheduled legacy |
| `transactions.created.v1` | `transactions.handle_transaction_side_effects` | evalua sobrelimite y puede crear alerta | visible en `/api/alerts/alertas/` si excede limite |
| `transactions.updated.v1` | `transactions.handle_transaction_side_effects` | solo actua si la transaccion se vuelve contable | visible indirectamente segun deuda/alerta |
| `transactions.financial.updated.v1` | `transactions.handle_transaction_side_effects` | reconcilia deuda y estado de scheduled legacy | visible indirectamente en deudas/scheduled payments |
| `transactions.financial.updated.v1` | `transactions.handle_transaction_side_effects` | vuelve a evaluar sobrelimite | visible en alertas si aplica |
| `transactions.confirmed.v1` | `transactions.handle_transaction_side_effects` | aplica a deuda y scheduled legacy | visible indirectamente |
| `transactions.confirmed.v1` | `transactions.handle_transaction_side_effects` | evalua sobrelimite | visible en alertas si aplica |
| `transactions.participant.created.v1` | `transactions.handle_participant_side_effects` | recalcula `contacts_contact.net_balance` | visible en modulo de contactos, no en inbox/realtime |
| `transactions.participant.updated.v1` | `transactions.handle_participant_side_effects` | recalcula `contacts_contact.net_balance` | visible en contactos |
| `transactions.participant.deleted.v1` | `transactions.handle_participant_side_effects` | recalcula `contacts_contact.net_balance` | visible en contactos |
| `transactions.participant.settled.v1` | `transactions.handle_participant_side_effects` | recalcula `contacts_contact.net_balance` | visible en contactos |
| `transactions.scheduled_payment.created.v1` | `transactions.handle_scheduled_payment_projection` | sincroniza slice de scheduled payments en usage projection | visible en identidad/capabilities |
| `transactions.scheduled_payment.updated.v1` | `transactions.handle_scheduled_payment_projection` | sincroniza usage projection | visible en identidad |
| `transactions.scheduled_payment.deleted.v1` | `transactions.handle_scheduled_payment_projection` | sincroniza usage projection | visible en identidad |
| `transactions.scheduled_payment.paid.v1` | `transactions.handle_scheduled_payment_projection` | sincroniza usage projection | visible en identidad |

### Conclusion de transactions

Hoy `transactions` reacciona bien localmente, pero la mayoria de sus efectos
visibles terminan en:

- alertas por sobrelimite
- cambios de deuda
- cambios en contactos
- projection de identidad

No tiene hoy una capa dedicada de notificaciones o realtime para
`transactions.*`.

## 3. Payments

### Resumen

Los listeners locales de `payments` estan muy orientados a UX ligera:

- `RealtimeSignal`
- `UserProductUsageProjection`

La materializacion a ledger no depende de listeners. Ocurre en el mismo
servicio de pagos cuando el estado pasa a `succeeded` o `settled`.

### Matriz exacta

| Evento | Listener local | Side effect interno | Efecto visible |
|---|---|---|---|
| `payments.intent.created.v1` | `payments.publish_intent_created_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.intent.created.v1` | `users.refresh_usage_projection_from_payments` | delta de usage de pagos | visible en identidad |
| `payments.intent.dispatched.v1` | `payments.publish_intent_dispatched_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.intent.dispatched.v1` | `users.refresh_usage_projection_from_payments` | delta de usage | visible en identidad |
| `payments.intent.requires_action.v1` | `payments.publish_intent_requires_action_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.intent.requires_action.v1` | `users.refresh_usage_projection_from_payments` | delta de usage | visible en identidad |
| `payments.intent.processing.v1` | `payments.publish_intent_processing_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.intent.processing.v1` | `users.refresh_usage_projection_from_payments` | delta de usage | visible en identidad |
| `payments.intent.succeeded.v1` | `payments.publish_intent_succeeded_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.intent.succeeded.v1` | `users.refresh_usage_projection_from_payments` | delta de usage | visible en identidad |
| `payments.intent.settled.v1` | `payments.publish_intent_settled_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.intent.settled.v1` | `users.refresh_usage_projection_from_payments` | delta de usage | visible en identidad |
| `payments.intent.failed.v1` | `payments.publish_intent_failed_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.intent.failed.v1` | `users.refresh_usage_projection_from_payments` | delta de usage | visible en identidad |
| `payments.intent.cancelled.v1` | `payments.publish_intent_cancelled_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.intent.cancelled.v1` | `users.refresh_usage_projection_from_payments` | delta de usage | visible en identidad |
| `payments.intent.reversed.v1` | `payments.publish_intent_reversed_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.intent.disputed.v1` | `payments.publish_intent_disputed_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.payout.requested.v1` | `payments.publish_payout_requested_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.payout.requested.v1` | `users.refresh_usage_projection_from_payments` | delta de usage de payouts | visible en identidad |
| `payments.payout.succeeded.v1` | `payments.publish_payout_succeeded_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.payout.succeeded.v1` | `users.refresh_usage_projection_from_payments` | delta de usage de payouts | visible en identidad |
| `payments.payout.failed.v1` | `payments.publish_payout_failed_realtime_signal` | crea `RealtimeSignal` | visible en realtime |
| `payments.payout.failed.v1` | `users.refresh_usage_projection_from_payments` | delta de usage de payouts | visible en identidad |

### Importante en payments

Estos efectos no salen de listeners sino del servicio de dominio:

- `mark_payment_intent_succeeded()` materializa `Transaction`
- `mark_payment_intent_settled()` materializa `Transaction`

Eso significa que el ledger no depende de consumir `payments.intent.succeeded`
en otro modulo. El pago aterriza en `transactions` antes de que el evento se
publique.

### Conclusion de payments

Hoy `payments` produce bien:

- realtime
- usage projection

Pero no tiene aun una capa local fuerte de notificaciones in-app basada en
`payments.*`.

## 4. Identity

### Resumen

`identity` es el contexto con mas fan-out local transversal.

Sus eventos alimentan:

- bootstrap del usuario
- grants y permisos
- cuentas
- sesiones
- consentimientos
- usage projection
- alertas de bienvenida

### Matriz exacta

| Evento | Listener local | Side effect interno | Efecto visible |
|---|---|---|---|
| `users.registered.v1` | `users.bootstrap_registered_user` | bootstrap propio del usuario | visible indirectamente en setup inicial |
| `users.registered.v1` | `users.bootstrap_registered_user` | refresh de usage projection | visible en `/api/identity/users/me/` y dashboard |
| `users.registered.v1` | `identity.permissions.sync_plan_permissions_on_register` | crea grants segun plan | visible indirectamente en capabilities |
| `users.registered.v1` | `accounts.bootstrap_user_financial_home` | crea hogar financiero base del usuario | visible en `/api/finance/accounts/cuentas/` |
| `users.onboarding.completed.v1` | `users.create_onboarding_completion_alert` | crea alertas de bienvenida | visible en alertas |
| `users.plan.changed.v1` | `identity.permissions.sync_plan_permissions_on_change` | resincroniza grants por plan | visible indirectamente en capabilities |
| `users.plan.changed.v1` | `accounts.handle_user_plan_changed` | refresh de proyeccion/inteligencia de cuentas | visible indirectamente en dashboard |
| `users.currency.changed.v1` | `accounts.handle_user_currency_changed` | sincroniza moneda base a cuentas | visible indirectamente en cuentas/dashboard |
| `users.suspended.v1` | `identity.sessions.revoke_all_active_user_sessions` | revoca sesiones activas | visible como invalidacion de acceso |
| `users.suspended.v1` | `accounts.handle_user_suspended` | deshabilita auto sync del usuario | visible indirectamente en integraciones/sync |
| `users.activated.v1` | `accounts.handle_user_activated` | refresh de proyeccion/inteligencia de cuentas | visible indirectamente |
| `users.consent.granted.v1` | `identity.permissions.sync_consent_permissions_granted` | actualiza grants por consentimiento | visible indirectamente en capabilities |
| `users.consent.granted.v1` | `identity.consents.refresh_accounts_after_consent_granted` | refresca proyeccion de cuentas del usuario | visible indirectamente |
| `users.consent.revoked.v1` | `identity.permissions.sync_consent_permissions_revoked` | revoca grants ligados a consentimiento | visible indirectamente en capabilities |
| `users.consent.revoked.v1` | `identity.consents.disable_revoked_open_banking_sync` | deshabilita auto sync y coordina teardown | visible indirectamente en integraciones/sync |
| `users.permission.revoked.v1` | `accounts.handle_user_permission_revoked` | revoca acceso a integracion por provider si corresponde | visible indirectamente en cuentas sincronizadas |
| `users.device.revoked.v1` | `identity.sessions.revoke_device_sessions` | revoca sesiones del dispositivo | visible como invalidacion de acceso |
| `users.social_identity.unlinked.v1` | `identity.sessions.revoke_unlinked_provider_sessions` | revoca sesiones del provider desvinculado | visible como invalidacion de acceso |
| `alerts.ai.enriched.v1` | `users.refresh_usage_projection_from_alert_ai_enriched` | suma/delta de uso de IA | visible en identidad |
| `accounts.*` | `users.refresh_usage_projection_from_accounts` | actualiza usage projection por cuentas y membresias | visible en identidad |
| `payments.*` | `users.refresh_usage_projection_from_payments` | actualiza usage projection por pagos y payouts | visible en identidad |

### Eventos de identity sin consumidor local claro hoy

En el codigo auditado no encontre listeners locales registrados para:

- `users.profile.updated.v1`
- `users.verified.v1`
- `users.social_auth.prepared.v1`
- `users.device.registered.v1`
- `users.device.trusted.v1`
- `users.session.started.v1`
- `users.session.revoked.v1`
- `users.permission.granted.v1`
- `users.permission.denied.v1`
- `growth.upgrade_triggered.v1`

Eso no significa que esten mal como contrato, sino que hoy:

- o no tienen fan-out local todavia
- o solo sirven como contrato futuro para consumidores externos
- o requieren endurecer su uso dentro del backend

### Observacion sobre `devices` y `social_identities`

Hoy:

- `identity.devices` no registra listeners locales en `ready()`
- `identity.social_identities` tampoco registra listeners locales propios

Los efectos asociados a esos eventos viven mas en:

- `identity.sessions`
- emisores del dominio

que en listeners dedicados de esos submodulos.

## Lectura operativa final

### Que ya funciona bien en local

- consumo local de `identity` para bootstrap, permissions y sessions
- consumo local de `accounts` para intelligence, usage projection y algunos
  side effects visibles
- consumo local de `transactions` para deudas, alerts y contacts
- consumo local de `payments` para realtime y usage projection

### Que es visible de inmediato al usuario

Lo mas visible hoy por listeners locales:

- `Alert`
- `NotificationDelivery`
- `RealtimeSignal`
- cambios en `UserProductUsageProjection`

### Que es interno pero importante

Muchos eventos reaccionan en capas que no siempre se ven enseguida en Postman:

- refresh de inteligencia
- grants de permisos
- revocacion de sesiones
- disable auto sync
- reconciliacion de deuda
- net balance de contactos

### Huecos reales del sistema actual

1. `accounts.created.v1` no tiene una señal visible propia de UX hoy.
2. `transactions.*` no alimenta notificaciones o realtime de forma rica.
3. `payments.*` no genera inbox durable local hoy; solo realtime y usage.
4. varios eventos de `identity` siguen definidos pero sin consumidor local.

## Recomendaciones

1. Definir una matriz canonica de "evento visible" vs "evento solo interno".
2. Decidir si `accounts.created.v1` debe generar:
   - notificacion
   - realtime
   - o solo seguir siendo interno
3. Decidir si `transactions.created.v1` debe producir algun feedback UX
   adicional.
4. Decidir si `payments.intent.failed.v1` y `payments.intent.succeeded.v1`
   deben generar tambien `NotificationDelivery`.
5. Limpiar `common.domain_events` para separar:
   - eventos catalogados y usados hoy
   - eventos definidos pero todavia sin consumidor

## Plan de endurecimiento

## 1. Eventos que deberian ser visibles al usuario

Estos eventos no deberian quedarse solo como concern interno. Deberian
terminar, segun el caso, en:

- `NotificationDelivery`
- `RealtimeSignal`
- `Alert`
- o reflejo claro en `dashboard`/`me`

### Accounts

- `accounts.created.v1`
  - recomendado: `RealtimeSignal`
  - opcional: `NotificationDelivery` solo si la UX necesita confirmacion de
    alta de cuenta
  - razon: hoy crear una cuenta nueva casi no deja feedback visible
- `accounts.external.linked.v1`
  - recomendado: `NotificationDelivery`
  - recomendado: `RealtimeSignal`
  - razon: conectar una cuenta externa es una accion de alto valor para el
    usuario
- `accounts.external.unlinked.v1`
  - recomendado: `NotificationDelivery`
  - razon: perder una integracion es relevante y debe verse
- `accounts.sync.failed.v1`
  - ya produce `Alert`
  - recomendado adicional: `NotificationDelivery` si se quiere inbox durable
- `accounts.balance.drift.detected.v1`
  - ya produce `Alert`
  - correcto mantenerlo visible porque implica inconsistencia operativa seria

### Transactions

- `transactions.created.v1`
  - recomendado: `RealtimeSignal` cuando el movimiento sea manual o importado
  - opcional: `NotificationDelivery` solo para casos de alto valor o compartidos
- `transactions.financial.updated.v1`
  - recomendado: `RealtimeSignal` cuando cambia monto, cuenta o fecha de un
    movimiento ya contable
- `transactions.imported.v1`
  - recomendado: `NotificationDelivery` resumida por lote o sync, no una por
    transaccion
  - recomendado: `RealtimeSignal` agregada
- `transactions.reimbursement.recorded.v1`
  - recomendado: `NotificationDelivery` si el reembolso es una accion explicita
    del usuario

### Payments

- `payments.intent.requires_action.v1`
  - ya tiene `RealtimeSignal`
  - recomendado adicional: `NotificationDelivery`
  - razon: requiere intervencion del usuario
- `payments.intent.failed.v1`
  - ya tiene `RealtimeSignal`
  - recomendado adicional: `NotificationDelivery`
  - razon: fallo de pago debe quedar en inbox durable
- `payments.intent.succeeded.v1`
  - ya tiene `RealtimeSignal`
  - recomendado adicional: `NotificationDelivery` configurable
- `payments.intent.reversed.v1`
  - ya tiene `RealtimeSignal`
  - recomendado: `Alert` o `NotificationDelivery` de alta prioridad
- `payments.intent.disputed.v1`
  - ya tiene `RealtimeSignal`
  - recomendado: `Alert` + `NotificationDelivery`

### Identity

- `users.plan.changed.v1`
  - recomendado: `NotificationDelivery`
  - razon: un cambio de plan es visible para el usuario
- `growth.upgrade_triggered.v1`
  - recomendado: visible en UI como upgrade hint, no necesariamente inbox
- `users.suspended.v1`
  - visible por efecto de logout/revocacion; no hace falta notificacion in-app
  - si existe canal externo, podria usarse email

## 2. Eventos que deben seguir siendo internos

Estos eventos hoy tienen mas sentido como concern interno/operativo y no
deberian volverse notificacion o realtime salvo que cambie el producto.

### Accounts

- `accounts.recalculated.v1`
- `accounts.balance.snapshot.created.v1`
- `accounts.sync.scheduled.v1`
- `accounts.sync.status.changed.v1`
- `accounts.sync.started.v1`

### Transactions

- `transactions.updated.v1`
  - salvo que el cambio sea relevante de cara al usuario
- `transactions.participant.updated.v1`
- `transactions.participant.deleted.v1`
- `transactions.scheduled_payment.updated.v1`

### Payments

- `payments.fee.calculated.v1`
- `payments.provider.reference.recorded.v1`
- `payments.callback.received.v1`
- `payments.settlement.recorded.v1`

### Identity

- `users.permission.granted.v1`
- `users.permission.denied.v1`
- `users.permission.revoked.v1`
- `users.session.started.v1`
- `users.session.revoked.v1`

## 3. Eventos del catalogo actual que sobran, siguen viejos o estan subutilizados

No significa que haya que borrarlos hoy mismo del codigo, pero si conviene
marcarlos como:

- reservados
- no usados aun
- o candidatos a limpieza del catalogo central

### Candidatos por no tener consumidor local claro hoy

- `users.profile.updated.v1`
- `users.verified.v1`
- `users.social_auth.prepared.v1`
- `users.device.registered.v1`
- `users.device.trusted.v1`
- `users.session.started.v1`
- `users.session.revoked.v1`
- `users.permission.granted.v1`
- `users.permission.denied.v1`
- `growth.upgrade_triggered.v1`
- `insight.generated.v1`
- `ml.anomaly.detected.v1`

### Problema del catalogo actual

En `common.domain_events` hoy conviven:

- eventos vivos y usados
- eventos reservados sin consumidor
- eventos comentados de roadmap

Eso hace que el archivo mezcle:

- contrato operativo real
- intencion futura
- historial editorial

### Recomendacion de gobierno

Separar conceptualmente en tres grupos:

1. `operational_event_catalog`
   - solo eventos emitidos o consumidos hoy
2. `reserved_event_catalog`
   - nombres apartados para roadmap
3. `deprecated_or_legacy_event_catalog`
   - contratos viejos o superseded

## 4. Eventos nuevos y recomendados mas avanzados

Estos no deberian agregarse todos de una vez. Son propuesta de endurecimiento.
Cada uno deberia entrar solo si tiene:

- emisor claro
- owner de dominio
- payload definido
- consumidor o caso de uso real

## Accounts propuestos

- `accounts.integration.health.changed.v1`
  - cuando una integracion pasa de sana a degradada o viceversa
  - util para soporte, dashboard y provider health
- `accounts.sync.degraded.v1`
  - para distinguir fallo puntual de degradacion sostenida
- `accounts.sync.cursor.advanced.v1`
  - interno, util para observabilidad de ingest
- `accounts.shared.visibility.changed.v1`
  - si el sharing gana reglas de visibilidad mas ricas
- `accounts.access.policy.changed.v1`
  - para cambios efectivos de acceso, no solo membership CRUD

## Transactions propuestos

- `transactions.import.batch.received.v1`
  - lote recibido desde open banking/import
- `transactions.import.batch.applied.v1`
  - lote aplicado al ledger
- `transactions.import.batch.failed.v1`
  - lote fallido
- `transactions.deduplicated.v1`
  - cuando un movimiento fue descartado por duplicado
- `transactions.corrected.v1`
  - cuando una transaccion fue corregida por fuente externa
- `transactions.reversed.v1`
  - cuando el movimiento se revierte de forma contable
- `transactions.reconciled.v1`
  - cuando pasa a estado reconciliado real con fuente externa
- `transactions.classification.changed.v1`
  - si categoria/vendor/tags se vuelven relevantes para projections o ML
- `transactions.shared.expense.settled.v1`
  - si shared expenses crece como dominio fuerte

## Payments propuestos

- `payments.intent.timeout.v1`
  - cuando el intent expira sin resolverse
- `payments.intent.retry.scheduled.v1`
  - si el sistema agenda retry operacional
- `payments.intent.reconciliation.mismatch.v1`
  - mismatch entre callback, settlement y estado local
- `payments.provider.degraded.v1`
  - degradacion general del proveedor
- `payments.provider.recovered.v1`
  - recuperacion del proveedor
- `payments.callback.invalid_signature.v1`
  - callback rechazado por firma invalida
- `payments.payout.instruction.failed.v1`
  - granularidad por instruccion, no solo por batch
- `payments.payout.instruction.succeeded.v1`
  - granularidad por instruccion

## Identity propuestos

- `users.step_up.required.v1`
  - cuando una accion sensible exige verificacion adicional
- `users.step_up.completed.v1`
  - cuando esa verificacion adicional se completa
- `users.risk.state.changed.v1`
  - cuando cambia el estado de riesgo del usuario/dispositivo
- `users.device.suspicious.v1`
  - cuando un dispositivo se marca como sospechoso
- `users.consent.teardown.completed.v1`
  - cuando la revocacion de consentimiento ya desarmo la integracion
- `users.capabilities.recomputed.v1`
  - si quieres distinguir grants/permisos de la vista final de capabilities

## 5. Plan por fases

### Fase 1: visibilidad UX inmediata

- hacer visible `accounts.created.v1`
- agregar inbox durable para `payments.intent.failed.v1`
- agregar inbox durable para `payments.intent.requires_action.v1`
- decidir si `transactions.created.v1` merece realtime basico

### Fase 2: gobierno del catalogo

- marcar en documentacion los eventos vivos
- marcar los reservados
- marcar los eventos sin consumidor actual
- limpiar comentarios viejos de roadmap dentro de `common.domain_events`

### Fase 3: endurecimiento de integraciones

- introducir `transactions.import.*`
- introducir `transactions.corrected.v1`
- introducir `payments.intent.reconciliation.mismatch.v1`
- introducir `users.consent.teardown.completed.v1`
- introducir `accounts.integration.health.changed.v1`

### Fase 4: experiencia y seguridad avanzada

- introducir `users.step_up.required.v1`
- introducir `users.device.suspicious.v1`
- introducir `payments.provider.degraded.v1`
- introducir `payments.provider.recovered.v1`

## Criterio final

Antes de agregar un evento nuevo al catalogo central, deberia responderse:

1. quien lo emite
2. cual es el aggregate o entidad dueña
3. si es visible al usuario o solo interno
4. que payload minimo y estable necesita
5. quien lo consume hoy
6. si debe vivir en realtime, inbox, alertas, projections o solo observabilidad

Si no responde bien esas preguntas, conviene dejarlo como propuesta
documentada y no meterlo aun en `common.domain_events`.
