# finance.transactions

## Que hace

Ledger transaccional y pagos programados locales.

Este modulo registra movimientos financieros y side effects contables
relacionados. No debe asumir por si mismo la orquestacion del rail externo.

## Regla principal

`Transaction` es el reflejo contable final.

No es:

- el `PaymentIntent`
- el callback del proveedor
- la referencia operativa del rail

Eso vive en `payments`.

## Flujos principales

### Transaccion manual o importada

Sigue funcionando igual:

- manual
- importada
- OCR
- open finance
- reimbursement

### Pago externo confirmado

1. `payments.payment_intents` confirma el resultado
2. `finance.transactions.payment_materialization_service`
   crea o reutiliza una `Transaction`
3. balances, reportes y ledger reaccionan como siempre

La regla sigue siendo:

- el PSP, fees, CUS y referencias viven en `payments`
- `transactions` guarda el reflejo contable y el vinculo ligero con
  `payment_intent`

## Relacion con otros modulos

- `finance.accounts`: recalcula balances
- `alerts.alerts`: genera alertas locales
- `payments.payment_intents`: origen canonico de pagos externos
- `payments.scheduled_payments`: planificacion nueva

## Estado actual

`Transaction` ahora puede referenciar opcionalmente un `PaymentIntent`.

Eso permite:

- mantener el ledger limpio
- conservar trazabilidad con el pago externo
- evitar duplicar toda la semantica PSP dentro de la transaccion

`ScheduledPayment.generar_transaccion` sigue siendo un flujo local/manual.

## Esqueleto/futuro

Todavia falta:

- exponer mejor la relacion `Transaction <-> PaymentIntent` en serializers/API
- migrar gradualmente la planificacion hacia `payments.scheduled_payments`
- enriquecer conciliacion entre rail externo y ledger
