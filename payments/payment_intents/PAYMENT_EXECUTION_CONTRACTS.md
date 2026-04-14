# Contratos Canonicos De Ejecucion De Pago

## Objetivo

Este documento define los contratos canonicos de ejecucion del rail en
`payments.payment_intents`.

No describe el reflejo contable final.

Ese reflejo pertenece a `finance.transactions` y se documenta aparte en:

- [RAIL_NORMALIZATION_CONTRACTS.md](/D:/Vexxo_Backend_API/finance/transactions/RAIL_NORMALIZATION_CONTRACTS.md)

## Regla principal

`payments` es dueno de:

- creacion del intent
- autorizacion
- captura
- settlement
- callbacks
- reversals
- refunds
- disputes
- metadata de wallet o PSP
- riesgo y resultados operativos del rail

`transactions` solo recibe el reflejo contable final cuando el movimiento ya es
valido para ledger.

## Contrato 1: `payment_execution.normalized_payload`

### Uso

Representa el estado operativo del pago en un PSP, gateway, banco o wallet.

### Campos obligatorios

```json
{
  "provider": "wompi",
  "provider_intent_id": "wpi_001",
  "payment_type": "payin",
  "rail": "payment_network",
  "status": "processing",
  "amount": "50000.00",
  "currency": "COP",
  "idempotency_key": "idem-001"
}
```

### Campos recomendados

```json
{
  "provider_event_id": "evt_001",
  "provider_reference": "ref_001",
  "authorization_reference": "auth_001",
  "capture_reference": "cap_001",
  "settlement_reference": "set_001",
  "wallet_provider": "google_pay",
  "payment_method_type": "card",
  "card_network": "visa",
  "card_last4": "4242",
  "token_type": "gateway_token",
  "fee_amount": "1500.00",
  "tax_amount": "285.00",
  "authorized_at": "2026-04-14T10:00:00-05:00",
  "captured_at": "2026-04-14T10:01:00-05:00",
  "settled_at": "2026-04-14T10:05:00-05:00",
  "requires_action_payload": {},
  "risk_result": {
    "decision": "allow",
    "score": 12
  },
  "raw_payload": {},
  "metadata": {
    "merchant_transaction_id": "order-001"
  }
}
```

### Semantica

- `status` describe el estado operativo del rail, no el estado del ledger
- `wallet_provider` solo aplica cuando el rail use wallet
- `raw_payload` conserva el callback o payload original del proveedor
- este contrato puede mutar varias veces antes de producir un reflejo contable

## Contrato 2: `payment_callback.normalized_payload`

### Uso

Representa un webhook o callback autenticado del proveedor.

### Campos obligatorios

```json
{
  "provider": "wompi",
  "provider_event_id": "evt_001",
  "callback_type": "payment_status",
  "status": "accepted",
  "received_at": "2026-04-14T10:02:00-05:00"
}
```

### Campos recomendados

```json
{
  "provider_intent_id": "wpi_001",
  "signature_valid": true,
  "normalized_status": "succeeded",
  "raw_payload": {},
  "metadata": {
    "delivery_attempt": 1
  }
}
```

## Contrato 3: `payment_settlement.normalized_payload`

### Uso

Representa el cierre contable u operativo del PSP antes del reflejo final al
ledger.

### Campos obligatorios

```json
{
  "provider": "wompi",
  "provider_settlement_id": "set_001",
  "provider_intent_id": "wpi_001",
  "status": "settled",
  "settled_amount": "50000.00",
  "currency": "COP",
  "settled_at": "2026-04-14T10:05:00-05:00"
}
```

## Relacion con `finance.transactions`

La frontera entre ambos contextos es esta:

1. `payments` ejecuta el rail
2. `payments` estabiliza el estado operativo
3. `payments` decide si el movimiento ya es reflejable
4. `transactions` materializa el reflejo contable con
   `payment_reflection.normalized_payload`

## Matriz de mapeo

La matriz concreta por proveedor vive en:

- [integrations/provider_mappings/payment_execution/](/D:/Vexxo_Backend_API/integrations/provider_mappings/payment_execution)

## Documentos relacionados

- [INTEGRATION_SOURCE_CATALOG.md](/D:/Vexxo_Backend_API/INTEGRATION_SOURCE_CATALOG.md)
- [payments/payment_intents/README.md](/D:/Vexxo_Backend_API/payments/payment_intents/README.md)
