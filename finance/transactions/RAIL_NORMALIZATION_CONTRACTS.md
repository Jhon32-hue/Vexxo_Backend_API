# Contratos Canonicos De Normalizacion Por Rail

## Objetivo

Este documento define el contrato canonico que debe usar Vexxo para
normalizar movimientos externos antes de materializarlos en ledger.

No es un contrato de proveedor.

Es un contrato interno de Vexxo para evitar que:

- `normalized_payload` dependa del primer agregador integrado
- cada consumer tenga que entender payloads distintos
- `raw_payload` se convierta en el contrato operativo real
- `transactions` y `payments` mezclen responsabilidades

## Regla principal

Hay dos capas distintas:

1. `payments.payment_intents`
- duena de la ejecucion del rail
- callbacks
- autorizacion, captura, settlement, dispute, reversal
- referencias del PSP, wallet o payment network

2. `finance.transactions`
- duena del reflejo contable final
- intake externo canonico
- dedupe, reconciliacion y enrichment normalizado del ledger

Por eso, en rails de pago no basta un solo contrato.

Se necesitan dos:

- contrato de ejecucion del rail en `payments`
- contrato de reflejo contable en `transactions`

## Tipos de contrato

Hoy conviene formalizar estos contratos:

1. `open_banking.normalized_payload`
2. `message_inferred.normalized_payload`
3. `voice_inferred.normalized_payload`
4. `payment_reflection.normalized_payload`

Y en paralelo, fuera de `transactions`:

5. `payment_execution.normalized_payload`

El `5` vive en `payments.payment_intents`, no aqui.

## Reglas de diseno

- `raw_payload` siempre se conserva
- `normalized_payload` debe ser estable entre proveedores
- `Transaction` guarda el subconjunto canonico transversal
- `TransactionExternalDetails` guarda enrichment rico por rail
- `TransactionIntakeReceipt` guarda staging e idempotencia
- si un campo no existe en un proveedor, se deja vacio; no se inventa semantica
- si un dato es inferido, debe venir marcado con `data_origin` y `confidence_score`

## Contrato 1: `open_banking.normalized_payload`

### Uso

Para movimientos provenientes de agregadores bancarios, open finance o
conectores bancarios con semantica cercana al ledger.

### Campos obligatorios

```json
{
  "account_id": 123,
  "external_id": "provider-txn-001",
  "provider_status": "booked",
  "type": "expense",
  "status": "posted",
  "amount": "12500.00",
  "date": "2026-04-10",
  "currency": "COP"
}
```

### Campos recomendados

```json
{
  "description": "Compra supermercado",
  "transaction_information": {
    "provider_description": "COMPRA TARJETA SUPERMERCADO UNO"
  },
  "booking_datetime": "2026-04-10T10:15:00-05:00",
  "value_datetime": "2026-04-10T10:15:00-05:00",
  "credit_debit_indicator": "debit",
  "merchant_name": "Supermercado Uno",
  "merchant_category_code": "5411",
  "counterparty_name": "Supermercado Uno SAS",
  "counterparty_account_ref": "",
  "rail": "open_banking",
  "rail_reference": "bank-ref-7788",
  "balance_after_transaction": "540000.25",
  "original_amount": "12500.00",
  "original_currency": "COP",
  "fx_rate": "1.00000000",
  "country_code": "CO",
  "channel": "api",
  "data_origin": "open_banking",
  "confidence_score": 98,
  "raw_payload": {},
  "metadata": {
    "consent_id": "consent-123",
    "connection_id": "conn-001",
    "provider_cursor": "cursor-xyz"
  }
}
```

### Semantica

- `type` es la interpretacion canonica de Vexxo
- `status` es el estado contable interno
- `provider_status` conserva el estado del agregador
- `rail` debe ser `open_banking`
- `data_origin` debe ser `open_banking`
- `confidence_score` normalmente alta: `90-100`

### Donde termina

- resumen transversal en `Transaction`
- detalle rico en `TransactionExternalDetails`
- idempotencia en `TransactionSourceLink`

## Contrato 2: `message_inferred.normalized_payload`

### Uso

Para SMS, email u otras fuentes textuales inferidas por parser.

### Campos obligatorios

```json
{
  "account_id": 123,
  "external_id": "sms-001",
  "provider_status": "inferred_pending_confirmation",
  "type": "expense",
  "status": "pending",
  "amount": "24900.00",
  "date": "2026-04-10",
  "currency": "COP",
  "rail": "message",
  "channel": "sms",
  "data_origin": "inferred",
  "confidence_score": 72
}
```

### Campos obligatorios de inferencia

```json
{
  "message_id": "sms-001",
  "sender_id": "BANCOXYZ",
  "received_at": "2026-04-10T18:22:00-05:00",
  "parsed_text": "Compra por $24.900 en FARMATODO",
  "parser_version": "transactions.message_parser.v1",
  "needs_user_confirmation": true,
  "inference_status": "needs_confirmation"
}
```

### Campos recomendados

```json
{
  "description": "Compra en FARMATODO",
  "merchant_name": "FARMATODO",
  "counterparty_name": "",
  "raw_payload": {},
  "metadata": {
    "parser": "transactions.message_parser.v1"
  }
}
```

### Semantica

- `status` debe iniciar como `pending`
- `confirmed` debe iniciar como `false`
- `needs_user_confirmation=true` es obligatorio
- `data_origin=inferred` es obligatorio
- `confidence_score` expresa calidad del parser, no certeza bancaria

### Donde termina

- se persiste en `Transaction`
- no es countable para ledger mientras siga `pending + confirmed=false`
- `TransactionExternalDetails` guarda el rastro completo de inferencia

## Contrato 3: `voice_inferred.normalized_payload`

### Uso

Para notas de voz transcritas y estructuradas por un worker interno de voz o
futuro `llm_gateway`.

Este contrato modela intencion del usuario, no evidencia bancaria.

El punto de entrada operativo no es el CRUD manual ni el intake interno directo
desde mobile. Mobile crea una `TransactionInferenceRequest`; el worker procesa
esa solicitud y solo entonces `transactions` aplica este contrato por intake
canonico.

El cliente publico no envia este payload normalizado. El `POST` publico de voz
solo envia referencia y metadatos del audio; `voice_inferred.normalized_payload`
es un contrato interno entre el worker de IA y `finance.transactions`.

En local, ese worker interno debe correr como proceso durable separado y tomar
solicitudes desde BD; no como thread efimero del request web.

### Campos obligatorios

```json
{
  "account_id": 123,
  "external_id": "voice-note-001:item-001",
  "provider_status": "inferred_pending_confirmation",
  "type": "expense",
  "status": "pending",
  "amount": "24900.00",
  "date": "2026-04-10",
  "currency": "COP",
  "confirmed": false,
  "rail": "manual",
  "channel": "voice",
  "data_origin": "inferred",
  "confidence_score": 82
}
```

### Campos obligatorios de inferencia

```json
{
  "message_id": "voice-note-001:item-001",
  "sender_id": "user-audio",
  "received_at": "2026-04-10T18:22:00-05:00",
  "parsed_text": "Registra un gasto de 24.900 en farmacia",
  "parser_version": "transactions.voice_parser.v1",
  "needs_user_confirmation": true,
  "inference_status": "needs_confirmation"
}
```

### Campos recomendados

```json
{
  "description": "Compra en farmacia",
  "merchant_name": "Farmacia",
  "counterparty_name": "",
  "raw_payload": {
    "audio_object_ref": "gs://bucket/voice-note-001.m4a",
    "transcript_confidence": 0.91
  },
  "metadata": {
    "parser": "transactions.voice_parser.v1",
    "language": "es-CO"
  }
}
```

### Semantica

- `rail=manual` porque el usuario esta declarando un movimiento
- `channel=voice` identifica la captura original
- `status` debe iniciar como `pending`
- `confirmed` debe iniciar como `false`
- `needs_user_confirmation=true` es obligatorio
- `data_origin=inferred` es obligatorio
- si una nota contiene varias transacciones, se envia como batch con una fila
  por movimiento inferido
- el `idempotency_key` del batch se deriva de la solicitud de inferencia para
  evitar duplicados por retry
- el worker debe ignorar solicitudes fuera de `queued` para no reprocesar
  resultados tardios sobre estados terminales
- la operacion debe exponer metricas de despacho y recuperacion stale separadas
  de las fallas de negocio del modelo

### Donde termina

- `TransactionInferenceRequest` conserva estado, audio, errores, retries y
  vinculo al batch
- se persiste en `Transaction`
- no es countable para ledger mientras siga `pending + confirmed=false`
- `TransactionExternalDetails` guarda transcripcion, parser y evidencia de audio

## Contrato 4: `payment_reflection.normalized_payload`

### Uso

Para el reflejo contable de un pago ya confirmado o liquidado en un rail
externo.

Este contrato no reemplaza el detalle operativo del PSP.

Ese detalle vive en `payments.payment_intents`.

### Campos obligatorios

```json
{
  "account_id": 123,
  "external_id": "intent-001-ledger",
  "provider_status": "settled",
  "type": "expense",
  "status": "posted",
  "amount": "50000.00",
  "date": "2026-04-10",
  "currency": "COP",
  "rail": "payment_network",
  "channel": "ecommerce",
  "data_origin": "payment_intent",
  "confidence_score": 100
}
```

### Campos recomendados

```json
{
  "description": "Pago confirmado comercio aliado",
  "rail_reference": "gateway-ref-001",
  "authorization_status": "authorized",
  "settlement_status": "settled",
  "authorized_at": "2026-04-10T11:00:00-05:00",
  "captured_at": "2026-04-10T11:01:00-05:00",
  "settled_at": "2026-04-10T11:05:00-05:00",
  "merchant_name": "Comercio Aliado",
  "country_code": "CO",
  "raw_payload": {},
  "metadata": {
    "payment_intent_id": "pi-001",
    "provider": "stripe",
    "wallet_provider": "google_pay"
  }
}
```

### Semantica

- `data_origin` debe ser `payment_intent` o `payment_network`
- `rail` debe reflejar el rail contable visible:
  - `payment_network`
  - `wallet`
  - `bank_transfer`
  - `card`
- `confidence_score` suele ser alta porque ya viene de flujo operativo confirmado

### Donde termina

- `payments` conserva el detalle rico del rail
- `transactions` conserva el reflejo contable final y sus campos consultables

## Contrato 5: `payment_execution.normalized_payload`

### Uso

Este contrato no pertenece a `transactions`.

Pertenece a `payments.payment_intents`.

Sirve para modelar:

- autorizacion
- captura
- settlement
- callback del proveedor
- refund
- reversal
- dispute
- risk metadata

### Campos tipicos

- `provider_intent_id`
- `provider_event_id`
- `provider_reference`
- `wallet_provider`
- `token_type`
- `card_network`
- `last4`
- `authorization_reference`
- `capture_reference`
- `settlement_reference`
- `requires_action_payload`
- `fees_breakdown`
- `tax_breakdown`
- `risk_result`

### Regla

Lo operativo vive en `payments`.

Solo el reflejo contable confirmado pasa a `transactions`.

## Matriz de mapeo inicial

| Fuente | Contrato canonico | Bounded context duenio | Notas |
|---|---|---|---|
| Belvo transactions | `open_banking.normalized_payload` | `finance.transactions` | intake bancario canonico |
| Plaid transactions | `open_banking.normalized_payload` | `finance.transactions` | intake bancario canonico |
| TrueLayer transactions | `open_banking.normalized_payload` | `finance.transactions` | intake bancario canonico |
| SMS Banco X | `message_inferred.normalized_payload` | `finance.transactions` | parser + confirmacion usuario |
| Email Banco X | `message_inferred.normalized_payload` | `finance.transactions` | parser + confirmacion usuario |
| Nota de voz mobile | `voice_inferred.normalized_payload` | `finance.transactions` | transcripcion + IA + confirmacion usuario |
| Google Pay + PSP | `payment_execution.normalized_payload` | `payments.payment_intents` | detalle operativo del rail |
| PSP settled callback | `payment_execution.normalized_payload` | `payments.payment_intents` | settlement y callback |
| PaymentIntent materialized | `payment_reflection.normalized_payload` | `finance.transactions` | reflejo final en ledger |

## Niveles de confianza

### `95-100`

Fuente operativa altamente confiable:

- payment intent confirmado/settled
- open banking bien identificado

### `80-94`

Fuente externa confiable con enrichment parcial:

- open banking sin merchant robusto
- import estructurado validado

### `50-79`

Fuente inferida util pero no definitiva:

- sms/email con monto, tipo y contraparte parcial
- voz con monto, tipo y descripcion extraidos por IA

### `0-49`

Fuente debil o ambigua:

- parser sin monto claro
- texto ambiguo
- import incompleto

Regla operativa:

- menor a `80`: revisar confirmacion del usuario
- menor a `50`: no materializar automaticamente salvo decision explicita

## Siguiente paso real

Con este contrato cerrado, lo siguiente ya no es discutir nombres de campos.

Lo siguiente es crear matrices por proveedor:

- `Belvo -> open_banking.normalized_payload`
- `Plaid -> open_banking.normalized_payload`
- `Google Pay + PSP -> payment_execution.normalized_payload`
- `PaymentIntent -> payment_reflection.normalized_payload`
- `SMS Banco X -> message_inferred.normalized_payload`
- `Voice AI -> voice_inferred.normalized_payload`

Ese paso si exige leer documentacion oficial o muestras reales por proveedor.



## Frontera documental de `payment_execution`

`payment_execution.normalized_payload` ya no debe tratarse como propiedad
principal de `finance.transactions`.

Su documento canonico vive en:

- [PAYMENT_EXECUTION_CONTRACTS.md](/D:/Vexxo_Backend_API/payments/payment_intents/PAYMENT_EXECUTION_CONTRACTS.md)

En `transactions` solo se mantiene la referencia a esa frontera para dejar clara
la separacion entre:

- ejecucion del rail en `payments`
- reflejo contable en `transactions`

