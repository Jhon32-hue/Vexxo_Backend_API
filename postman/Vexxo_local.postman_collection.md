# Vexxo Local Postman Collection

Fuente importable para Postman: [Vexxo_local.postman_collection.json](/c:/Users/Alamb/Documents/Vexxo_Backend_API/postman/Vexxo_local.postman_collection.json)

Este archivo unifica la colección JSON con una guía humana de uso. Cada request queda documentado con:
- método
- URL
- si requiere `Bearer`
- headers
- body
- variables que llena para los siguientes requests

## Base local

- `base_url`: `http://127.0.0.1:8000`
- API base típica: `http://127.0.0.1:8000/api/`

## Variables de colección

| Variable | Valor inicial | Uso |
|---|---|---|
| `base_url` | `http://127.0.0.1:8000` | Base del backend local |
| `email` | `prueba@example.com` | Usuario de prueba |
| `password` | `Secret12345!` | Password de prueba |
| `access_token` | `""` | JWT de acceso |
| `refresh_token` | `""` | JWT de refresh |
| `account_id` | `""` | Id de cuenta creada |
| `transaction_id` | `""` | Id de transacción creada |
| `alert_id` | `""` | Id de alerta helper |
| `notification_id` | `""` | Id de notificación helper |
| `payment_intent_id` | `""` | Id de payment intent |
| `internal_token` | `""` | Token interno para endpoints internos |

## Flujo recomendado

1. `Auth / Register`
2. `Auth / Login`
3. `Identity / Me`
4. `Accounts / Create Account`
5. `Transactions / Create Transaction`
6. Luego `Payments`, `Alerts`, `Notifications` y `Realtime`

## Reglas de autenticación

- Endpoints públicos de auth:
  - no usan `Authorization: Bearer`
- Endpoints autenticados:
  - usan `Authorization: Bearer {{access_token}}`
- Endpoints internos:
  - usan `X-Vexxo-Internal-Token: {{internal_token}}`

## 00 - Start Here

Carpeta informativa en Postman. No contiene requests funcionales.

## 01 - Auth

### Register

- Método: `POST`
- URL: `{{base_url}}/api/identity/users/auth/register/`
- Bearer: `No`
- Headers:
  - `Content-Type: application/json`
- Body:

```json
{
  "full_name": "Usuario Prueba",
  "email": "{{email}}",
  "password": "{{password}}",
  "password2": "{{password}}",
  "preferred_currency": "COP",
  "timezone_name": "America/Bogota",
  "locale": "es_CO"
}
```

- Descripción:
  - crea un usuario nuevo
  - si el correo ya existe, puedes seguir directo con `Login`

### Login

- Método: `POST`
- URL: `{{base_url}}/api/identity/users/auth/login/`
- Bearer: `No`
- Headers:
  - `Content-Type: application/json`
- Body:

```json
{
  "username": "{{email}}",
  "password": "{{password}}"
}
```

- Descripción:
  - acepta email o username en `username`
- Variables que llena automáticamente si responde `200`:
  - `access_token = data.access`
  - `refresh_token = data.refresh`

### Refresh

- Método: `POST`
- URL: `{{base_url}}/api/identity/users/auth/refresh/`
- Bearer: `No`
- Headers:
  - `Content-Type: application/json`
- Body:

```json
{
  "refresh": "{{refresh_token}}"
}
```

## 02 - Identity

### Me

- Método: `GET`
- URL: `{{base_url}}/api/identity/users/me/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Dashboard

- Método: `GET`
- URL: `{{base_url}}/api/identity/users/dashboard/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 03 - Accounts

### List Accounts

- Método: `GET`
- URL: `{{base_url}}/api/finance/accounts/cuentas/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Create Account

- Método: `POST`
- URL: `{{base_url}}/api/finance/accounts/cuentas/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
  - `Content-Type: application/json`
- Body:

```json
{
  "name": "Cuenta Postman",
  "currency": "COP",
  "type": "cash",
  "ownership": "personal"
}
```

- Variables que llena automáticamente si responde `201`:
  - `account_id = data.id`

### List Account Memberships

- Método: `GET`
- URL: `{{base_url}}/api/finance/accounts/membresias-cuenta/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 04 - Transactions

### List Transactions

- Método: `GET`
- URL: `{{base_url}}/api/finance/transactions/transactions/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Create Transaction

- Método: `POST`
- URL: `{{base_url}}/api/finance/transactions/transactions/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
  - `Content-Type: application/json`
- Body:

```json
{
  "account": {{account_id}},
  "type": "expense",
  "status": "posted",
  "amount": "25000.00",
  "date": "2026-04-06",
  "notes": "Prueba desde Postman",
  "confirmed": true
}
```

- Requiere:
  - `account_id` ya definido
- Variables que llena automáticamente si responde `201`:
  - `transaction_id = data.id`

### Confirm Transaction

- Método: `POST`
- URL: `{{base_url}}/api/finance/transactions/transactions/{{transaction_id}}/marcar_confirmada/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 05 - Payments

### List Payment Intents

- Método: `GET`
- URL: `{{base_url}}/api/payments/intents/intents/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Pricing Preview

- Método: `POST`
- URL: `{{base_url}}/api/payments/intents/intents/pricing-preview/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
  - `Content-Type: application/json`
- Body:

```json
{
  "amount": "30000.00",
  "provider": "wompi",
  "rail": "other",
  "country": "CO",
  "payment_type": "other"
}
```

### Create Payment Intent

- Método: `POST`
- URL: `{{base_url}}/api/payments/intents/intents/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
  - `Content-Type: application/json`
- Body:

```json
{
  "account": {{account_id}},
  "amount": "30000.00",
  "currency": "COP",
  "provider": "wompi",
  "payment_type": "other",
  "rail": "other",
  "external_reference": "postman-order-001",
  "invoice_reference": "invoice-001",
  "beneficiary_name": "Comercio Demo",
  "beneficiary_document": "900123456",
  "beneficiary_account_ref": "benef-001",
  "idempotency_key": "postman-intent-001"
}
```

- Requiere:
  - `account_id` ya definido
- Variables que llena automáticamente si responde `201`:
  - `payment_intent_id = data.id`

### Retrieve Payment Intent

- Método: `GET`
- URL: `{{base_url}}/api/payments/intents/intents/{{payment_intent_id}}/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### List Payouts

- Método: `GET`
- URL: `{{base_url}}/api/payments/intents/payouts/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Create Payout Batch

- Método: `POST`
- URL: `{{base_url}}/api/payments/intents/payouts/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
  - `Content-Type: application/json`
- Body:

```json
{
  "provider": "wompi",
  "rail": "bank_transfer",
  "currency": "COP",
  "instructions": [
    {
      "beneficiary_name": "Proveedor Demo",
      "beneficiary_document": "900999111",
      "beneficiary_account_ref": "acct-001",
      "amount": "10000.00",
      "external_reference": "postman-payout-001"
    }
  ]
}
```

### List Payment Outbox

- Método: `GET`
- URL: `{{base_url}}/api/payments/intents/outbox-pagos/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### List Callback Receipts

- Método: `GET`
- URL: `{{base_url}}/api/payments/intents/callback-receipts/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### List Settlements

- Método: `GET`
- URL: `{{base_url}}/api/payments/intents/settlements/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### List Operational Cases

- Método: `GET`
- URL: `{{base_url}}/api/payments/intents/operational-cases/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Provider Contracts

- Método: `GET`
- URL: `{{base_url}}/api/payments/intents/providers/contracts/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 06 - Alerts

### List Alerts

- Método: `GET`
- URL: `{{base_url}}/api/alerts/alertas/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Get First Alert Id Helper

- Método: `GET`
- URL: `{{base_url}}/api/alerts/alertas/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`
- Variables que llena automáticamente si responde `200` y la respuesta es lista con datos:
  - `alert_id = data[0].id`

### Mark Alert Read

- Método: `POST`
- URL: `{{base_url}}/api/alerts/alertas/{{alert_id}}/mark_read/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Mark Alert Resolved

- Método: `POST`
- URL: `{{base_url}}/api/alerts/alertas/{{alert_id}}/mark_resolved/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Snooze Alert

- Método: `POST`
- URL: `{{base_url}}/api/alerts/alertas/{{alert_id}}/snooze/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
  - `Content-Type: application/json`
- Body:

```json
{
  "until": "2026-04-07T09:00:00-05:00"
}
```

## 07 - Notifications

### List Deliveries

- Método: `GET`
- URL: `{{base_url}}/api/notifications/deliveries/entregas-notificacion/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Get First Notification Id Helper

- Método: `GET`
- URL: `{{base_url}}/api/notifications/deliveries/entregas-notificacion/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`
- Variables que llena automáticamente si responde `200` y la respuesta es lista con datos:
  - `notification_id = data[0].id`

### Mark Delivery Read

- Método: `POST`
- URL: `{{base_url}}/api/notifications/deliveries/entregas-notificacion/{{notification_id}}/mark_read/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Mark All Read

- Método: `POST`
- URL: `{{base_url}}/api/notifications/deliveries/entregas-notificacion/mark_all_read/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Delivery Stats

- Método: `GET`
- URL: `{{base_url}}/api/notifications/deliveries/entregas-notificacion/stats/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 08 - Realtime

### List Signals

- Método: `GET`
- URL: `{{base_url}}/api/realtime/consumers/senales-realtime/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Latest Signal

- Método: `GET`
- URL: `{{base_url}}/api/realtime/consumers/senales-realtime/latest/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Signal Stats

- Método: `GET`
- URL: `{{base_url}}/api/realtime/consumers/senales-realtime/stats/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 09 - Support

### Audit Log

- Método: `GET`
- URL: `{{base_url}}/api/support/audit/auditoria/`
- Bearer: `Sí`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 10 - Internal

Estos endpoints no usan `Bearer`. Usan token interno.

### Alerts AI Worker

- Método: `POST`
- URL: `{{base_url}}/api/alerts/internal/ai-worker/`
- Bearer: `No`
- Headers:
  - `X-Vexxo-Internal-Token: {{internal_token}}`
  - `Content-Type: application/json`
- Body:

```json
{
  "alert_id": {{alert_id}},
  "trigger": "postman"
}
```

### Internal Account Sync Stub

- Método: `POST`
- URL: `{{base_url}}/internal/integrations/banks/accounts/sync/`
- Bearer: `No`
- Headers:
  - `X-Vexxo-Internal-Token: {{internal_token}}`
  - `Content-Type: application/json`
- Body:

```json
{
  "account_id": {{account_id}},
  "mode": "success",
  "sync_cursor": "cursor-postman-001",
  "duration_ms": 250,
  "provider_metadata": {
    "source": "postman"
  }
}
```

### Internal Account Intelligence Refresh

- Método: `POST`
- URL: `{{base_url}}/internal/integrations/banks/accounts/intelligence/refresh/`
- Bearer: `No`
- Headers:
  - `X-Vexxo-Internal-Token: {{internal_token}}`
  - `Content-Type: application/json`
- Body:

```json
{
  "owner_id": 1
}
```

## Resumen rápido por request

| Grupo | Request | Método | URL | Auth |
|---|---|---|---|---|
| Auth | Register | `POST` | `/api/identity/users/auth/register/` | sin bearer |
| Auth | Login | `POST` | `/api/identity/users/auth/login/` | sin bearer |
| Auth | Refresh | `POST` | `/api/identity/users/auth/refresh/` | sin bearer |
| Identity | Me | `GET` | `/api/identity/users/me/` | bearer |
| Identity | Dashboard | `GET` | `/api/identity/users/dashboard/` | bearer |
| Accounts | List Accounts | `GET` | `/api/finance/accounts/cuentas/` | bearer |
| Accounts | Create Account | `POST` | `/api/finance/accounts/cuentas/` | bearer |
| Accounts | List Account Memberships | `GET` | `/api/finance/accounts/membresias-cuenta/` | bearer |
| Transactions | List Transactions | `GET` | `/api/finance/transactions/transactions/` | bearer |
| Transactions | Create Transaction | `POST` | `/api/finance/transactions/transactions/` | bearer |
| Transactions | Confirm Transaction | `POST` | `/api/finance/transactions/transactions/{{transaction_id}}/marcar_confirmada/` | bearer |
| Payments | List Payment Intents | `GET` | `/api/payments/intents/intents/` | bearer |
| Payments | Pricing Preview | `POST` | `/api/payments/intents/intents/pricing-preview/` | bearer |
| Payments | Create Payment Intent | `POST` | `/api/payments/intents/intents/` | bearer |
| Payments | Retrieve Payment Intent | `GET` | `/api/payments/intents/intents/{{payment_intent_id}}/` | bearer |
| Payments | List Payouts | `GET` | `/api/payments/intents/payouts/` | bearer |
| Payments | Create Payout Batch | `POST` | `/api/payments/intents/payouts/` | bearer |
| Payments | List Payment Outbox | `GET` | `/api/payments/intents/outbox-pagos/` | bearer |
| Payments | List Callback Receipts | `GET` | `/api/payments/intents/callback-receipts/` | bearer |
| Payments | List Settlements | `GET` | `/api/payments/intents/settlements/` | bearer |
| Payments | List Operational Cases | `GET` | `/api/payments/intents/operational-cases/` | bearer |
| Payments | Provider Contracts | `GET` | `/api/payments/intents/providers/contracts/` | bearer |
| Alerts | List Alerts | `GET` | `/api/alerts/alertas/` | bearer |
| Alerts | Get First Alert Id Helper | `GET` | `/api/alerts/alertas/` | bearer |
| Alerts | Mark Alert Read | `POST` | `/api/alerts/alertas/{{alert_id}}/mark_read/` | bearer |
| Alerts | Mark Alert Resolved | `POST` | `/api/alerts/alertas/{{alert_id}}/mark_resolved/` | bearer |
| Alerts | Snooze Alert | `POST` | `/api/alerts/alertas/{{alert_id}}/snooze/` | bearer |
| Notifications | List Deliveries | `GET` | `/api/notifications/deliveries/entregas-notificacion/` | bearer |
| Notifications | Get First Notification Id Helper | `GET` | `/api/notifications/deliveries/entregas-notificacion/` | bearer |
| Notifications | Mark Delivery Read | `POST` | `/api/notifications/deliveries/entregas-notificacion/{{notification_id}}/mark_read/` | bearer |
| Notifications | Mark All Read | `POST` | `/api/notifications/deliveries/entregas-notificacion/mark_all_read/` | bearer |
| Notifications | Delivery Stats | `GET` | `/api/notifications/deliveries/entregas-notificacion/stats/` | bearer |
| Realtime | List Signals | `GET` | `/api/realtime/consumers/senales-realtime/` | bearer |
| Realtime | Latest Signal | `GET` | `/api/realtime/consumers/senales-realtime/latest/` | bearer |
| Realtime | Signal Stats | `GET` | `/api/realtime/consumers/senales-realtime/stats/` | bearer |
| Support | Audit Log | `GET` | `/api/support/audit/auditoria/` | bearer |
| Internal | Alerts AI Worker | `POST` | `/api/alerts/internal/ai-worker/` | token interno |
| Internal | Internal Account Sync Stub | `POST` | `/internal/integrations/banks/accounts/sync/` | token interno |
| Internal | Internal Account Intelligence Refresh | `POST` | `/internal/integrations/banks/accounts/intelligence/refresh/` | token interno |
