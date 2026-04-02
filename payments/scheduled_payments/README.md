# payments.scheduled_payments

## Que hace

Este modulo modela la planificacion de pagos, no su ejecucion.

Aqui vive:

- `PaymentTemplate`: la plantilla recurrente o programada
- `PaymentScheduleRun`: la corrida concreta que puede generar un `PaymentIntent`

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

## Relacion con otros modulos

- `payments.payment_intents`: ejecuta el pago externo real
- `finance.transactions.ScheduledPayment`: modelo legacy/local de recordatorio
  y materializacion contable
- `finance.transactions`: recibe la transaccion final cuando el pago se confirma

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
- endpoints
- workers que conviertan corridas en intents
- linkage mas fino con el modelo legacy `transactions.ScheduledPayment`

## Nota de convivencia

Hoy el sistema todavia tiene `finance.transactions.ScheduledPayment`.

Ese modelo no se elimina de golpe para no romper funcionalidad actual.
`payments.scheduled_payments` es la capa nueva y mas limpia de planificacion.
