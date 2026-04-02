# payments

## Vision del bounded context

`payments` es la frontera de ejecucion externa de dinero en Vexxo.

Regla principal:

- pagar no es lo mismo que registrar una transaccion

Por eso el dominio se separa en:

- `payments.payment_intents`: intencion, ejecucion, callbacks, pricing y estado del rail
- `payments.scheduled_payments`: planificacion recurrente o programada
- `finance.transactions`: reflejo contable final en el ledger
- `payouts` se modela dentro de `payment_intents` por ahora mediante
  `PayoutBatch` y `PayoutInstruction`

## Flujos principales

### Pago saliente

1. el usuario pide pagar
2. nace `PaymentIntent`
3. el proveedor procesa
4. Vexxo recibe referencias/estado
5. se materializa `Transaction`

### Pago recurrente o programado

1. el usuario crea un template o convierte un pago exitoso en template
2. un scheduler pide una corrida
3. la corrida genera un `PaymentIntent`
4. el resultado confirmado se refleja en `Transaction`

### Dispersion

El modelo separa:

- pago saliente unitario
- lote de dispersion (`PayoutBatch`)
- instruccion individual (`PayoutInstruction`)

## Eventos

Desde aqui se definen eventos `payments.*` para:

- workers
- proyecciones de uso
- analytics
- futuras integraciones por Pub/Sub o Cloud Tasks

## Pricing y limites

El pricing canonico vive en `payments.payment_intents.pricing_service`.

Ese resolver separa:

- costo del proveedor
- impuestos del costo del proveedor
- fee de Vexxo
- impuestos del fee de Vexxo

Asi Vexxo puede:

- estimar el costo antes de pagar
- guardar un snapshot del precio usado al crear la orden
- comparar estimado vs callback real del PSP
- variar margen por plan, proveedor o rail

Los limites tambien se separan en dos capas:

- limites comerciales por plan:
  - monto maximo por pago
  - volumen diario
  - volumen mensual
  - cantidad mensual
  - payouts habilitados o no
- caps operativos internos por proveedor y rail:
  - cap maximo por instruccion
  - cap diario por proveedor/rail

Los caps operativos no representan upgrade. Representan proteccion de Vexxo
frente a conciliacion, fraude, reversos, soporte y salud del rail.

## Estado actual

El bounded context ya tiene:

- contratos de eventos `payments.*`
- `PaymentIntent`
- pricing base
- planificacion base
- materializacion contable base

Lo que falta despues:

- endpoints
- adapters PSP reales
- callbacks/webhooks
- outbox propio
- conciliacion y observabilidad mas profunda
