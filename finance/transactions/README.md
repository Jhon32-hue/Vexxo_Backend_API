# finance.transactions

## Que hace

`finance.transactions` es el ledger transaccional personal de Vexxo.

Su trabajo no es ejecutar rails externos ni hablar con PSPs. Su trabajo es:

- registrar el hecho contable final
- sostener balances, reportes y categorias
- servir como base para alerts, debts, contacts y proyecciones
- reflejar en ledger pagos externos ya confirmados por `payments`

## Rol en el negocio

Desde producto, este modulo representa la respuesta a preguntas como:

- "en que me gaste la plata"
- "que ingresos tuve"
- "que paso realmente en esta cuenta"
- "este pago externo ya quedo registrado en mi historial"
- "cuanto me debe este contacto o cuanto le debo"

Es el punto donde Vexxo deja de hablar de intenciones y pasa a hablar de realidad contable.

## Que no hace

`Transaction` no es:

- un `PaymentIntent`
- un callback de proveedor
- una corrida programada
- el transporte de eventos
- el rail externo

Eso vive en otros bounded contexts:

- `payments.payment_intents`: intencion, ejecucion, callback, settlement, dispute
- `payments.scheduled_payments`: planificacion recurrente o programada
- `finance.accounts`: balance operativo y relacion con cuentas

## Modelos principales

### `Transaction`

Representa un movimiento financiero final del ledger.

Campos importantes:

- `type`: `expense`, `income`, `transfer`
- `status`: `pending`, `posted`, `reconciled`, `canceled`, `failed`
- `confirmed`: aceptacion de usuario o fuente confiable
- `affects_balance`: permite separar hechos contables de splits analiticos
- relaciones a `account`, `category`, `vendor`, `debt`, `installment`
- vinculo opcional a `payment_intent`
- metadata externa ligera: `source`, `provider`, `external_id`, `raw_payload`
- soporte de split y reembolso

### `ScheduledPayment`

Es el modelo legacy/local de recordatorio o programacion manual dentro de `transactions`.

No es el scheduler canonico para ejecucion externa.

Se mantiene para:

- recordatorios locales
- materializacion manual de un movimiento contable
- compatibilidad con deudas/cuotas y vistas legacy

### `TransactionParticipant`

Fuente canonica para participaciones humanas en una transaccion.

Ahora ya no hay dos modelos efectivos compitiendo. Esta clase cubre:

- contacto local opcional
- contraparte `linked_user`
- `direction` acreedor/deudor
- `share_amount`, `paid_amount`, `pending_amount`
- `status` operativo del share

Esto alimenta `contacts` y futuros escenarios de shared expenses.

### `TransactionDomainEventOutbox`

Outbox fuerte del bounded context `transactions`.

Se usa para:

- publicar `transactions.*` fuera del request path
- desacoplar listeners locales y dispatchers externos
- dejar workers dedicados para Cloud Run, Pub/Sub o jobs batch

## Semantica de `status + confirmed`

Esto quedo formalizado en el modelo y en `transaction_state_service.py`.

Reglas:

- `pending`: transaccion todavia no aceptada para ledger final
- `posted`: ya cuenta para ledger
- `reconciled`: ya fue conciliada y siempre implica `confirmed=True`
- `canceled` y `failed`: no deben afectar balance
- si una transaccion llega `confirmed=True` y sigue `pending`, se promueve a `posted`

Regla operativa:

- una transaccion cuenta para ledger cuando es `posted`/`reconciled`, esta `confirmed` y `affects_balance=True`

Eso evita ambiguedad entre "existe un registro" y "ya es verdad contable".

## Flujos principales

### 1. Transaccion manual o importada

1. la API crea o actualiza `Transaction`
2. serializer valida reglas de acceso a cuenta, tipo, deuda, categoria y limites
3. model normaliza `status + confirmed`
4. signal fino encola `transactions.*` en outbox
5. worker publica
6. listeners locales disparan side effects desacoplados

### 1.b. Transaccion en cuenta compartida

1. la cuenta visible no se resuelve solo por `owner`; se resuelve por
   `AccountMembership`
2. un usuario con acceso compartido puede leer transacciones de la cuenta si
   `accounts.permission_service.user_can_view_account()` lo permite
3. solo puede crear, editar, confirmar o borrar movimientos si
   `user_can_post_transactions()` lo permite
4. el ledger sigue quedando unificado bajo `account.owner`; el colaborador no
   crea un segundo ledger paralelo

Esto permite compartir la cuenta sin romper la verdad contable ni dividir el
historial por usuario colaborador.

### 2. Pago externo confirmado

1. `payments.payment_intents` procesa rail externo
2. cuando el pago ya es valido para ledger, `payment_materialization_service`
   crea o reutiliza `Transaction`
3. `transactions` queda como reflejo contable
4. el detalle rico del PSP sigue en `payments`

### 3. Pago programado legacy local

1. el usuario crea `transactions.ScheduledPayment`
2. si quiere materializarlo localmente, usa `generar_transaccion`
3. eso crea `Transaction` y marca el scheduled legacy como `paid`

Regla:

- este flujo es local/manual
- no reemplaza `payments.scheduled_payments`
- no ejecuta rails externos

### 4. Reembolso

1. el gasto original debe ser `expense` y `is_reimbursable=True`
2. el caso de uso registra una nueva `Transaction` de ingreso
3. el gasto original queda marcado como `reimbursed`
4. se emite evento de reembolso registrado

## Casos de uso movidos a servicios

La logica importante ya no depende solo de serializer o view action.

Servicios clave:

- `transaction_validation_service.py`
  - reglas de validacion de payload
  - ownership de FKs
  - limites de cuenta y plan
- `transaction_actions_service.py`
  - reasignar cuenta
  - confirmar transaccion
  - agregar comentario
  - registrar reembolso
  - materializar scheduled payment legacy
- `payment_materialization_service.py`
  - reflejo contable desde `payments`

## Eventos `transactions.*`

El contexto ya emite eventos canónicos como:

- `transactions.created.v1`
- `transactions.updated.v1`
- `transactions.financial.updated.v1`
- `transactions.deleted.v1`
- `transactions.confirmed.v1`
- `transactions.account.reassigned.v1`
- `transactions.reimbursement.recorded.v1`
- `transactions.participant.created.v1`
- `transactions.participant.updated.v1`
- `transactions.participant.deleted.v1`
- `transactions.participant.settled.v1`
- `transactions.scheduled_payment.created.v1`
- `transactions.scheduled_payment.updated.v1`
- `transactions.scheduled_payment.deleted.v1`
- `transactions.scheduled_payment.paid.v1`

### `transactions.financial.updated.v1`

Este evento existe para el caso en que una transaccion ya contable cambia
despues de haber entrado al ledger.

El payload ahora distingue:

- `financial_change.kind`
  - `cosmetic`
  - `became_countable`
  - `stopped_countable`
  - `updated_while_countable`
  - `updated_while_non_countable`
- `financial_change.changed_fields`
- `countable_before`
- `countable_for_ledger`

Con esto un consumidor puede diferenciar un cambio material de monto, fecha,
cuenta, deuda o estado contable frente a un cambio solo visual o auxiliar.

### Actor y trazabilidad de CRUD

Los eventos normales de CRUD ya no dependen solo de atributos efimeros puestos
despues del `save()`.

`transactions` usa un contexto de actor por request/accion para que:

- `transactions.created.v1`
- `transactions.updated.v1`
- `transactions.financial.updated.v1`
- `transactions.deleted.v1`
- eventos de participantes
- eventos de scheduled payments legacy

propaguen `actor_user_id` de forma consistente cuando la mutacion nace desde
API o acciones del backend.

## Que sigue en signal y que ya paso a eventos

### Signal

Los signals ahora son delgados.

Su responsabilidad principal es:

- capturar estado anterior
- detectar create/update/delete
- encolar evento en outbox

No deberian contener logica de negocio pesada.

### Event handlers

Los side effects relevantes se atienden desde listeners:

- aplicar pago a deudas cuando una transaccion se vuelve contable
- marcar scheduled payment legacy como pagado si corresponde
- crear alerta de over-spend si aplica
- recalcular net balance de contactos
- refrescar proyeccion de uso de scheduled payments

Regla actual importante:

- `transactions.financial.updated.v1` no reaplica automaticamente pagos a deuda
  para evitar duplicados sobre una transaccion ya contable
- ese evento existe para reconciliacion, observabilidad y futuros consumidores
  mas ricos; el balance incremental de `accounts` sigue resolviendose en su
  propio modulo

Cuando el update financiero toca deuda/cuota o scheduled payment legacy, el
listener ya ejecuta una correccion retroactiva acotada:

- reconstruye el estado de pagos de la deuda afectada desde el ledger real
- recompone el estado `paid/pending` del scheduled payment legacy segun
  transacciones contables existentes

Esto no reemplaza una conciliacion global del dominio, pero evita dejar objetos
derivados en estado viejo cuando una transaccion ya contable cambia despues.

Esto alinea `transactions` con el mismo estilo de `accounts` y `payments`.

## Convivencia entre `transactions.ScheduledPayment` y `payments.scheduled_payments`

La decision actual es explicita:

- `transactions.ScheduledPayment`
  - legacy/local
  - recordatorio y materializacion manual del ledger
  - compatibilidad con deudas/cuotas existentes

- `payments.scheduled_payments`
  - capa nueva y mas limpia de planificacion
  - genera `PaymentIntent`
  - orientada a ejecucion externa futura

No se mezclan:

- legacy scheduled no es rail externo
- payment schedule no es ledger final

## Relacion con otros modulos

- `finance.accounts`
  - consume transacciones para balance operativo
  - usa el ledger como fuente de verdad contable
- `finance.debts`
  - puede aplicar pagos cuando una transaccion de gasto se vuelve contable
- `contacts`
  - recalcula saldo neto desde `TransactionParticipant`
- `alerts.alerts`
  - genera alertas de over-spend a partir del ledger
- `payments.payment_intents`
  - ejecuta afuera, `transactions` refleja adentro
- `payments.scheduled_payments`
  - comparte la idea de programacion, pero no reemplaza el ledger
- `identity.users`
  - usa slices/proyecciones para limites y usage

## Encaje con GCP

`finance.transactions` esta pensado para operar asi:

- Cloud SQL: ledger OLTP y relaciones transaccionales
- API Gateway + Cloud Run API: comandos CRUD y acciones de negocio
- outbox + worker: publicacion confiable de `transactions.*`
- Pub/Sub / listeners externos: integraciones, pipelines y consumers
- BigQuery: analitica y reporting pesado fuera del request path

### Publicacion e idempotencia

El outbox de `transactions` usa:

- `idempotency_key` por evento
- `claim_for_processing()` antes de publicar para reducir doble despacho en
  workers concurrentes
- retry con backoff creciente antes de dead letter
- metadata como `projection_event_key` y `outbox_idempotency_key`

Esto es relevante en GCP cuando varios workers de Cloud Run o jobs manuales
pueden procesar el mismo lote casi al mismo tiempo.

### Latencia, retrasos y reconciliacion

`transactions` no asume entrega instantanea en todos los consumidores:

- el hecho contable queda persistido primero en Cloud SQL
- `accounts` actualiza balance cacheado por delta incremental en el mismo flujo
- el outbox publica despues
- consumidores, alertas y proyecciones pueden llegar con retraso sin perder el
  hecho base

Si hay latencia o retraso, el ledger sigue siendo la verdad; lo derivado se
considera eventualmente consistente.

Regla clave:

- Cloud SQL guarda el hecho contable
- workers y projections resuelven derivaciones
- BigQuery absorbe analitica grande

## Consultas y performance

Este modulo no debe usarse para analitica pesada en caliente.

Uso correcto:

- lectura puntual por usuario/cuenta/mes
- joins razonables para ledger operacional
- proyecciones y snapshots para UI derivada
- filtros por `year`, `month`, `day`, `date_from`, `date_to` y `scope`
  (`owned/shared/all`) para evitar scans amplios desde mobile

Uso incorrecto:

- exploracion global pesada
- agregaciones cross-tenant desde OLTP
- reporting grande en request path

## Estado actual

Ya existe:

- modelo contable rico
- relacion limpia con `payment_intent`
- un solo `TransactionParticipant` efectivo
- semantica formal de `status + confirmed`
- outbox propio
- claim explicito e idempotencia de publicacion en outbox
- servicios de accion
- acceso a transacciones compartidas segun memberships de cuenta
- filtros temporales explicitos para consumo movil
- propagacion consistente de `actor_user_id` en CRUD normal
- reconciliacion retroactiva minima para deuda y scheduled payment legacy
- listeners desacoplados

## Pendientes reales

- materializar migraciones del app si el repo todavia no las tiene completas
- endurecer maquina de estados si en el futuro aparecen mas fuentes de ingestion
- mover mas casos de uso de reporte/presupuesto a eventos `transactions.*`
- definir productores canonicos adicionales si `budgets`, `reports` o `goals`
  empiezan a depender mas del ledger
