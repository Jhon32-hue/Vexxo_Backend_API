# Wompi

## Clasificacion

- categoria primaria: `payment_execution`
- categoria secundaria: `payment_reflection`
- bounded context principal: `payments.payment_intents`
- contrato canonico principal: `payment_execution.normalized_payload`

## Persistencia esperada

- `PaymentIntent`
- callback receipts
- settlement records
- reflejo posterior en `finance.transactions` si el estado ya es contable

## Reglas clave

- callbacks e idempotencia viven primero en `payments`
- `transactions` no debe recibir el callback crudo
- el reflejo final debe incluir `payment_intent_id`
