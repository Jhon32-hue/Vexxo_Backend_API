# payments.payment_intents

## Que hace

Este modulo es la frontera canonica de pagos externos en Vexxo.

Aqui vive:

- la intencion de pago (`PaymentIntent`)
- el estado del rail/proveedor
- referencias externas e internas
- pricing estimado y costos/fees/impuestos
- callbacks y transiciones de estado
- publicacion de eventos `payments.*`
- dispersiones:
  - `PayoutBatch`
  - `PayoutInstruction`

No es el ledger final. El ledger final vive en `finance.transactions`.

## Flujos principales

### Pay now

1. el usuario entra a pagos
2. se crea `PaymentIntent`
3. se calcula pricing estimado
4. se emiten:
   - `payments.order.requested.v1`
   - `payments.fee.calculated.v1`
   - `payments.intent.created.v1`
5. un adaptador/worker envia el comando al PSP
6. callbacks o workers actualizan estado:
   - `dispatched`
   - `processing`
   - `requires_action`
   - `succeeded`
   - `failed`
   - `cancelled`
   - `settled`
7. cuando el pago se confirma, se materializa `Transaction`

### Dispersion / payout

1. se crea `PayoutBatch`
2. cada salida se registra como `PayoutInstruction`
3. el guard comercial valida habilitacion, cantidad, monto, volumen diario y volumen mensual
4. el guard operativo valida caps internos por proveedor y rail
4. se emiten `payments.payout.*`
5. un integrador o worker ejecuta el rail real
6. el resultado individual se guarda por instruccion

### Metadata posterior del proveedor

Informacion como:

- referencia del proveedor
- CUS
- nombre del beneficiario
- impuestos
- breakdown de fees
- payload crudo del PSP

se guarda primero aqui, no en `finance.transactions`.

## Relacion con otros modulos

- `identity.users.services.product_access_service`: aplica limites y gating comercial
- `identity.users.services.product_usage_projection_service`: consume `payments.*`
  para conteo/volumen incremental
- `finance.transactions`: crea el reflejo contable final
- `payments.scheduled_payments`: puede generar `PaymentIntent` desde templates
- `integrations_stub` o futuros adapters: ejecutan el rail externo real

## Pricing

`pricing_service.py` separa:

- `provider_cost`
- `provider_tax`
- `vexxo_fee`
- `vexxo_tax`
- `total_fee`
- `total_charge`

Asi el costo se puede:

- mostrar antes del pago
- guardar como snapshot
- comparar con el callback real del proveedor
- ajustar por plan/proveedor/rail sin contaminar el ledger

En payouts aplica la misma idea:

- costo proveedor
- impuestos del costo
- fee Vexxo
- impuestos del fee

## Limites

El modulo distingue dos capas de limite:

- limite comercial por plan:
  - `max_single_payment_amount`
  - `max_daily_payment_volume`
  - `max_monthly_payment_volume`
  - `max_daily_payout_volume`
  - `max_monthly_payout_volume`
- cap operativo interno de Vexxo por proveedor y rail:
  - `platform_single_payment_cap`
  - `platform_daily_payment_cap`
  - `platform_single_payout_cap`
  - `platform_daily_payout_cap`

Los caps operativos no significan upgrade; significan proteccion operativa
frente a conciliacion, fraude, reversos, salud del rail y soporte.

## Estado actual

Ya existe:

- modelo `PaymentIntent`
- modelos base de dispersión:
  - `PayoutBatch`
  - `PayoutInstruction`
- calculo de pricing
- idempotencia de request
- publicacion de eventos `payments.*`
- materializacion contable al confirmar el pago
- servicios base de payout con guard y eventos

Todavia faltan:

- serializers y endpoints publicos/internos
- outbox propio del bounded context de pagos
- webhooks/callbacks del proveedor
- conciliacion externa completa
- endpoint de callback autenticado para PSP/retailer

## Nota importante

`finance.transactions.ScheduledPayment.generar_transaccion` no debe usarse como
semantica de pago externo. Ese flujo sigue siendo contable/manual.
