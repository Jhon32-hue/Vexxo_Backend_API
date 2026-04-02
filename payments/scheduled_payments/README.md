# payments.scheduled_payments

## Que hace

Este modulo modela la planificacion de pagos, no su ejecucion.

Aqui vive:

- `PaymentTemplate`: la plantilla recurrente o programada
- `PaymentScheduleRun`: la corrida concreta que puede generar un `PaymentIntent`

## Rol En El Producto

Esta capa permite que Vexxo no obligue al usuario a preregistrar siempre antes
de pagar, pero si le ofrezca orden y automatizacion cuando la necesite.

De cara al cliente, sirve para:

- programar pagos futuros
- repetir pagos ya realizados
- crear una disciplina operativa sin mezclar scheduling con el rail externo

## Flujos principales

### Programar antes de pagar

1. el usuario crea un `PaymentTemplate`
2. un scheduler o worker pide una corrida
3. `PaymentScheduleRun` representa la instancia concreta
4. `create_payment_intent_from_schedule_run(...)` genera el `PaymentIntent`
5. el rail externo se ejecuta desde `payments.payment_intents`

### Pagar ahora y convertir despues

1. el usuario paga ahora via `PaymentIntent`
2. despues Vexxo puede ofrecer convertir ese pago exitoso en template
3. `create_template_from_payment_intent(...)` copia los defaults relevantes

Este flujo es importante para app financiera personal porque no obliga a
preregistrar todo antes de pagar.

## Politicas Del Modulo

- planificar no es ejecutar
- una corrida puede terminar generando un intent, pero no equivale al pago real
- el resultado financiero final sigue viniendo de `payments.payment_intents`
- la materializacion contable final sigue entrando al ledger cuando el pago se
  confirma

## Relacion con otros modulos

- `payments.payment_intents`: ejecuta el pago externo real
- `finance.transactions.ScheduledPayment`: modelo legacy/local de recordatorio
  y materializacion contable
- `finance.transactions`: recibe la transaccion final cuando el pago se confirma

## Encaje Con GCP

La evolucion natural de este modulo es:

- Cloud Scheduler o workers de Cloud Run detectan runs pendientes
- Cloud Tasks dispara la ejecucion concreta
- el modulo genera `PaymentIntent`
- `payments.payment_intents` hace el trabajo externo

Eso evita mezclar scheduler, rail y ledger en una sola capa.

## Casos De Uso

- pago mensual de una factura
- transferencia recurrente a una cuenta propia
- tomar un pago exitoso y convertirlo en rutina mensual
- preparar una corrida futura y dejar que el rail se ejecute despues

## Estado actual

Ya existe:

- `PaymentTemplate`
- `PaymentScheduleRun`
- servicios para crear/actualizar templates
- servicio para pedir corridas recurrentes
- servicio para convertir una corrida en `PaymentIntent`
- servicio para convertir un pago exitoso en template

Todavia falta:

- scheduler real
- workers que conviertan corridas en intents automaticamente
- linkage mas fino con el modelo legacy `transactions.ScheduledPayment`

Ya existe API base para:

- CRUD de templates
- pedir una corrida
- materializar un `PaymentIntent` desde una corrida
- convertir un `PaymentIntent` exitoso en template

## Nota de convivencia

Hoy el sistema todavia tiene `finance.transactions.ScheduledPayment`.

Ese modelo no se elimina de golpe para no romper funcionalidad actual.
`payments.scheduled_payments` es la capa nueva y mas limpia de planificacion.
