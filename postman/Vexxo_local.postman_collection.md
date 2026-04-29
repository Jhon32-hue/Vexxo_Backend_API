# Vexxo Local Postman Collection

Fuente importable para Postman: [Vexxo_local.postman_collection.json](/c:/Users/Alamb/Documents/Vexxo_Backend_API/postman/Vexxo_local.postman_collection.json)

Este archivo unifica la coleccion JSON con una guia humana de uso. Cada request queda documentado con:
- metodo
- URL
- si requiere `Bearer`
- headers
- body
- variables que llena para los siguientes requests
- accion de usuario que representa

## Base local

- `base_url`: `http://127.0.0.1:8000`
- API base tipica: `http://127.0.0.1:8000/api/`

## Variables de coleccion

| Variable | Valor inicial | Uso |
|---|---|---|
| `base_url` | `http://127.0.0.1:8000` | Base del backend local |
| `email` | `prueba@example.com` | Usuario de prueba |
| `password` | `Secret12345!` | Password de prueba |
| `access_token` | `""` | JWT de acceso |
| `refresh_token` | `""` | JWT de refresh |
| `account_id` | `""` | Id de cuenta creada |
| `transaction_id` | `""` | Id de transaccion creada |
| `alert_id` | `""` | Id de alerta helper |
| `notification_id` | `""` | Id de notificacion helper |
| `payment_intent_id` | `""` | Id de payment intent |
| `internal_token` | `""` | Token interno para endpoints internos |

## Orden recomendado del frontend despues de login

Este es el orden normal para hidratar una app web o mobile de Vexxo:

1. `POST /api/identity/users/auth/login/`
   - obtiene `access` y `refresh`
2. `GET /api/identity/users/me/`
   - carga identidad, plan, moneda, locale y estado basico del usuario
3. `GET /api/identity/users/dashboard/`
   - carga vista agregada inicial del producto
4. `GET /api/finance/accounts/cuentas/`
   - carga cuentas visibles
5. `GET /api/finance/transactions/transactions/`
   - carga ledger o feed financiero
6. `GET /api/alerts/alertas/`
   - carga alertas visibles
7. `GET /api/notifications/deliveries/entregas-notificacion/`
   - carga inbox durable
8. `GET /api/realtime/consumers/senales-realtime/latest/`
   - trae la ultima senal de UX si quieres polling corto

## Para que sirve `me`

`GET /api/identity/users/me/` sirve para responder: "quien es el usuario autenticado y con que perfil entra al sistema ahora mismo".

Lo usas para:
- cargar la informacion del perfil
- saber el plan actual
- saber moneda preferida, timezone y locale
- decidir que features mostrar
- hidratar el store global del frontend despues de login

No lo usas para:
- cuentas
- dashboard financiero completo
- transacciones
- notificaciones

## Flujo recomendado de pruebas

1. `Auth / Register`
2. `Auth / Login`
3. `Identity / Me`
4. `Identity / Dashboard`
5. `Accounts / Create Account`
6. `Transactions / Create Transaction`
7. Luego `Payments`, `Alerts`, `Notifications` y `Realtime`

## Reglas de autenticacion

- Endpoints publicos de auth:
  - no usan `Authorization: Bearer`
- Endpoints autenticados:
  - usan `Authorization: Bearer {{access_token}}`
- Endpoints internos:
  - usan `X-Vexxo-Internal-Token: {{internal_token}}`

## 00 - Start Here

Carpeta informativa en Postman. No contiene requests funcionales.

## 01 - Auth

### Register

- Accion de usuario:
  - crear cuenta por primera vez
- Para que sirve:
  - alta inicial del usuario y bootstrap de identidad
- Metodo: `POST`
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

- Notas:
  - `password2` confirma la contrasena
  - si el correo ya existe, puedes seguir directo con `Login`

### Login

- Accion de usuario:
  - iniciar sesion
- Para que sirve:
  - obtener credenciales JWT para operar el resto del backend
- Metodo: `POST`
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

- Notas:
  - acepta email o username en `username`
- Variables que llena automaticamente si responde `200`:
  - `access_token = data.access`
  - `refresh_token = data.refresh`

### Refresh

- Accion de usuario:
  - renovar sesion sin volver a loguearse
- Para que sirve:
  - pedir un nuevo `access_token` cuando el anterior vence
- Metodo: `POST`
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

- Accion de usuario:
  - abrir la app y cargar el perfil actual
- Para que sirve:
  - saber quien soy dentro del sistema y con que configuracion entro
- Metodo: `GET`
- URL: `{{base_url}}/api/identity/users/me/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Dashboard

- Accion de usuario:
  - abrir la pantalla principal
- Para que sirve:
  - obtener una vista agregada inicial del estado del usuario dentro del producto
- Metodo: `GET`
- URL: `{{base_url}}/api/identity/users/dashboard/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 03 - Accounts

### List Accounts

- Accion de usuario:
  - ver mis cuentas
- Para que sirve:
  - cargar la lista de cuentas visibles para el usuario autenticado
- Metodo: `GET`
- URL: `{{base_url}}/api/finance/accounts/cuentas/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Create Account

- Accion de usuario:
  - crear una cuenta manual
- Para que sirve:
  - dar de alta una cuenta operativa sobre la que luego registras movimientos
- Metodo: `POST`
- URL: `{{base_url}}/api/finance/accounts/cuentas/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
  - `Content-Type: application/json`
- Body:

```json
{
  "name": "Cuenta Postman",
  "currency": "COP",
  "type": "cash",
  "ownership": "owned"
}
```

- Variables que llena automaticamente si responde `201`:
  - `account_id = data.id`

### List Account Memberships

- Accion de usuario:
  - revisar colaboracion o cuentas compartidas
- Para que sirve:
  - ver membresias efectivas y relaciones de acceso compartido
- Metodo: `GET`
- URL: `{{base_url}}/api/finance/accounts/membresias-cuenta/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 04 - Transactions

### List Transactions

- Accion de usuario:
  - ver mi historial de movimientos
- Para que sirve:
  - listar el ledger actual del usuario
- Metodo: `GET`
- URL: `{{base_url}}/api/finance/transactions/transactions/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Create Transaction

- Accion de usuario:
  - registrar un gasto, ingreso o transferencia manual
- Para que sirve:
  - crear un hecho contable en el ledger
- Metodo: `POST`
- URL: `{{base_url}}/api/finance/transactions/transactions/`
- Bearer: `Si`
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
- Variables que llena automaticamente si responde `201`:
  - `transaction_id = data.id`

### Confirm Transaction

- Accion de usuario:
  - confirmar un movimiento
- Para que sirve:
  - marcar una transaccion como confirmada cuando el flujo lo requiere
- Metodo: `POST`
- URL: `{{base_url}}/api/finance/transactions/transactions/{{transaction_id}}/marcar_confirmada/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Create Voice Inference Request

- Accion de usuario:
  - registrar una nota de voz para inferir transacciones
- Para que sirve:
  - crear una solicitud asincronica sin escribir ledger directo
- Metodo: `POST`
- URL: `{{base_url}}/api/finance/transactions/inference-requests/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
  - `Content-Type: application/json`
  - `X-Request-Id: postman-voice-request-001`
  - `Idempotency-Key: postman-voice-request-001`
- Body:

```json
{
  "account_id": {{account_id}},
  "audio_object_ref": "gs://vexxo-local-demo/audio/postman-voice-001.m4a",
  "audio_content_type": "audio/mp4",
  "audio_duration_ms": 8400,
  "language": "es-CO",
  "provider": "voice_ai"
}
```

- Requiere:
  - `account_id` ya definido
  - el backend solo acepta referencia y metadatos del audio; la inferencia
    estructurada la produce el worker interno
- Variables que llena automaticamente si responde `201` o `200`:
  - `inference_request_id = data.inference_request.id`

### List Voice Inference Requests

- Accion de usuario:
  - ver estado de solicitudes de voz
- Para que sirve:
  - consultar solicitudes `queued`, fallidas o aplicadas
- Metodo: `GET`
- URL: `{{base_url}}/api/finance/transactions/inference-requests/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Retry Voice Inference Request

- Accion de usuario:
  - reintentar una inferencia fallida
- Para que sirve:
  - reencolar solicitudes `transcription_failed`, `extraction_failed` o `dead_letter`
- Metodo: `POST`
- URL: `{{base_url}}/api/finance/transactions/inference-requests/{{inference_request_id}}/retry/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Reject Inferred Transaction

- Accion de usuario:
  - rechazar un borrador inferido
- Para que sirve:
  - cancelar una transaccion `pending` y `confirmed=false` sin usar PATCH ambiguo
- Metodo: `POST`
- URL: `{{base_url}}/api/finance/transactions/transactions/{{transaction_id}}/rechazar_inferida/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
  - `Content-Type: application/json`
- Body:

```json
{
  "reason": "No corresponde a un gasto real"
}
```

## 05 - Payments

### List Payment Intents

- Accion de usuario:
  - ver pagos iniciados o en proceso
- Para que sirve:
  - listar intents de pago del usuario
- Metodo: `GET`
- URL: `{{base_url}}/api/payments/intents/intents/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Pricing Preview

- Accion de usuario:
  - revisar cuanto costaria un pago antes de enviarlo
- Para que sirve:
  - calcular fees sin crear un payment intent
- Metodo: `POST`
- URL: `{{base_url}}/api/payments/intents/intents/pricing-preview/`
- Bearer: `Si`
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

- Accion de usuario:
  - iniciar un pago
- Para que sirve:
  - crear la intencion operativa del pago externo antes de su ejecucion real
- Metodo: `POST`
- URL: `{{base_url}}/api/payments/intents/intents/`
- Bearer: `Si`
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
- Variables que llena automaticamente si responde `201`:
  - `payment_intent_id = data.id`

### Retrieve Payment Intent

- Accion de usuario:
  - revisar el estado de un pago puntual
- Para que sirve:
  - consultar el detalle de un payment intent ya creado
- Metodo: `GET`
- URL: `{{base_url}}/api/payments/intents/intents/{{payment_intent_id}}/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### List Payouts

- Accion de usuario:
  - revisar lotes de dispersion
- Para que sirve:
  - listar batches de payout visibles
- Metodo: `GET`
- URL: `{{base_url}}/api/payments/intents/payouts/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Create Payout Batch

- Accion de usuario:
  - crear una dispersion o lote de pagos salientes
- Para que sirve:
  - registrar un batch operativo de payout
- Metodo: `POST`
- URL: `{{base_url}}/api/payments/intents/payouts/`
- Bearer: `Si`
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

- Accion de usuario:
  - observabilidad tecnica
- Para que sirve:
  - inspeccionar publicacion de eventos del contexto de pagos
- Metodo: `GET`
- URL: `{{base_url}}/api/payments/intents/outbox-pagos/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### List Callback Receipts

- Accion de usuario:
  - soporte operativo
- Para que sirve:
  - revisar callbacks recibidos desde proveedores
- Metodo: `GET`
- URL: `{{base_url}}/api/payments/intents/callback-receipts/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### List Settlements

- Accion de usuario:
  - soporte operativo o conciliacion
- Para que sirve:
  - revisar records de settlement
- Metodo: `GET`
- URL: `{{base_url}}/api/payments/intents/settlements/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### List Operational Cases

- Accion de usuario:
  - soporte de errores o disputas
- Para que sirve:
  - revisar casos operativos asociados a pagos
- Metodo: `GET`
- URL: `{{base_url}}/api/payments/intents/operational-cases/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Provider Contracts

- Accion de usuario:
  - inspeccion tecnica
- Para que sirve:
  - revisar contratos de provider expuestos por el backend
- Metodo: `GET`
- URL: `{{base_url}}/api/payments/intents/providers/contracts/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 06 - Alerts

### List Alerts

- Accion de usuario:
  - ver mis alertas
- Para que sirve:
  - listar alertas visibles del usuario
- Metodo: `GET`
- URL: `{{base_url}}/api/alerts/alertas/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Get First Alert Id Helper

- Accion de usuario:
  - helper de prueba en Postman
- Para que sirve:
  - capturar una `alert_id` para luego probar acciones sobre una alerta
- Metodo: `GET`
- URL: `{{base_url}}/api/alerts/alertas/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`
- Variables que llena automaticamente si responde `200` y la respuesta es lista con datos:
  - `alert_id = data[0].id`

### Mark Alert Read

- Accion de usuario:
  - marcar alerta como leida
- Para que sirve:
  - bajar el pendiente de lectura sobre una alerta concreta
- Metodo: `POST`
- URL: `{{base_url}}/api/alerts/alertas/{{alert_id}}/mark_read/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Mark Alert Resolved

- Accion de usuario:
  - cerrar o resolver una alerta
- Para que sirve:
  - cambiar el estado operativo de una alerta a resuelta
- Metodo: `POST`
- URL: `{{base_url}}/api/alerts/alertas/{{alert_id}}/mark_resolved/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Snooze Alert

- Accion de usuario:
  - posponer una alerta
- Para que sirve:
  - diferir la atencion de una alerta hasta una fecha dada
- Metodo: `POST`
- URL: `{{base_url}}/api/alerts/alertas/{{alert_id}}/snooze/`
- Bearer: `Si`
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

- Accion de usuario:
  - abrir inbox o centro de notificaciones
- Para que sirve:
  - listar entregas persistidas del usuario
- Metodo: `GET`
- URL: `{{base_url}}/api/notifications/deliveries/entregas-notificacion/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Get First Notification Id Helper

- Accion de usuario:
  - helper de prueba en Postman
- Para que sirve:
  - capturar una `notification_id` para luego probar acciones sobre una entrega
- Metodo: `GET`
- URL: `{{base_url}}/api/notifications/deliveries/entregas-notificacion/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`
- Variables que llena automaticamente si responde `200` y la respuesta es lista con datos:
  - `notification_id = data[0].id`

### Mark Delivery Read

- Accion de usuario:
  - marcar una notificacion como leida
- Para que sirve:
  - actualizar el estado de lectura de una entrega puntual
- Metodo: `POST`
- URL: `{{base_url}}/api/notifications/deliveries/entregas-notificacion/{{notification_id}}/mark_read/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Mark All Read

- Accion de usuario:
  - limpiar pendientes del inbox
- Para que sirve:
  - marcar varias notificaciones como leidas en una sola accion
- Metodo: `POST`
- URL: `{{base_url}}/api/notifications/deliveries/entregas-notificacion/mark_all_read/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Delivery Stats

- Accion de usuario:
  - revisar resumen del inbox
- Para que sirve:
  - consultar totales de notificaciones read y unread
- Metodo: `GET`
- URL: `{{base_url}}/api/notifications/deliveries/entregas-notificacion/stats/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 08 - Realtime

### List Signals

- Accion de usuario:
  - ver feed tecnico o debug de eventos UX
- Para que sirve:
  - listar senales realtime persistidas para el usuario
- Metodo: `GET`
- URL: `{{base_url}}/api/realtime/consumers/senales-realtime/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Latest Signal

- Accion de usuario:
  - polling corto desde frontend
- Para que sirve:
  - traer solo la ultima senal disponible
- Metodo: `GET`
- URL: `{{base_url}}/api/realtime/consumers/senales-realtime/latest/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

### Signal Stats

- Accion de usuario:
  - observabilidad ligera
- Para que sirve:
  - consultar resumen de cantidad total, canales y tipos de evento
- Metodo: `GET`
- URL: `{{base_url}}/api/realtime/consumers/senales-realtime/stats/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 09 - Support

### Audit Log

- Accion de usuario:
  - soporte o inspeccion operativa
- Para que sirve:
  - consultar auditoria funcional desde el backend
- Metodo: `GET`
- URL: `{{base_url}}/api/support/audit/auditoria/`
- Bearer: `Si`
- Headers:
  - `Authorization: Bearer {{access_token}}`
- Body: `sin body`

## 10 - Internal

Estos endpoints no usan `Bearer`. Usan token interno.

### Alerts AI Worker

- Accion de usuario:
  - debugging interno
- Para que sirve:
  - simular o disparar enriquecimiento IA de alertas
- Metodo: `POST`
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

- Accion de usuario:
  - debugging interno de sync bancario
- Para que sirve:
  - simular una corrida de sincronizacion bancaria desde el stub
- Metodo: `POST`
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

- Accion de usuario:
  - debugging interno de inteligencia de cuentas
- Para que sirve:
  - forzar un refresh de inteligencia para un owner concreto
- Metodo: `POST`
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

## Resumen rapido por request

| Grupo | Request | Accion de usuario | Metodo | URL | Auth |
|---|---|---|---|---|---|
| Auth | Register | Crear cuenta | `POST` | `/api/identity/users/auth/register/` | sin bearer |
| Auth | Login | Iniciar sesion | `POST` | `/api/identity/users/auth/login/` | sin bearer |
| Auth | Refresh | Renovar sesion | `POST` | `/api/identity/users/auth/refresh/` | sin bearer |
| Identity | Me | Cargar perfil actual | `GET` | `/api/identity/users/me/` | bearer |
| Identity | Dashboard | Abrir pantalla principal | `GET` | `/api/identity/users/dashboard/` | bearer |
| Accounts | List Accounts | Ver cuentas | `GET` | `/api/finance/accounts/cuentas/` | bearer |
| Accounts | Create Account | Crear cuenta | `POST` | `/api/finance/accounts/cuentas/` | bearer |
| Accounts | List Account Memberships | Ver cuentas compartidas | `GET` | `/api/finance/accounts/membresias-cuenta/` | bearer |
| Transactions | List Transactions | Ver historial | `GET` | `/api/finance/transactions/transactions/` | bearer |
| Transactions | Create Transaction | Registrar movimiento | `POST` | `/api/finance/transactions/transactions/` | bearer |
| Transactions | Confirm Transaction | Confirmar movimiento | `POST` | `/api/finance/transactions/transactions/{{transaction_id}}/marcar_confirmada/` | bearer |
| Payments | List Payment Intents | Ver pagos | `GET` | `/api/payments/intents/intents/` | bearer |
| Payments | Pricing Preview | Calcular fee | `POST` | `/api/payments/intents/intents/pricing-preview/` | bearer |
| Payments | Create Payment Intent | Iniciar pago | `POST` | `/api/payments/intents/intents/` | bearer |
| Payments | Retrieve Payment Intent | Ver estado de pago | `GET` | `/api/payments/intents/intents/{{payment_intent_id}}/` | bearer |
| Payments | List Payouts | Ver lotes de payout | `GET` | `/api/payments/intents/payouts/` | bearer |
| Payments | Create Payout Batch | Crear payout | `POST` | `/api/payments/intents/payouts/` | bearer |
| Payments | List Payment Outbox | Ver outbox pagos | `GET` | `/api/payments/intents/outbox-pagos/` | bearer |
| Payments | List Callback Receipts | Ver callbacks PSP | `GET` | `/api/payments/intents/callback-receipts/` | bearer |
| Payments | List Settlements | Ver settlements | `GET` | `/api/payments/intents/settlements/` | bearer |
| Payments | List Operational Cases | Ver errores y disputas | `GET` | `/api/payments/intents/operational-cases/` | bearer |
| Payments | Provider Contracts | Ver contratos PSP | `GET` | `/api/payments/intents/providers/contracts/` | bearer |
| Alerts | List Alerts | Ver alertas | `GET` | `/api/alerts/alertas/` | bearer |
| Alerts | Get First Alert Id Helper | Capturar alerta de prueba | `GET` | `/api/alerts/alertas/` | bearer |
| Alerts | Mark Alert Read | Marcar alerta leida | `POST` | `/api/alerts/alertas/{{alert_id}}/mark_read/` | bearer |
| Alerts | Mark Alert Resolved | Resolver alerta | `POST` | `/api/alerts/alertas/{{alert_id}}/mark_resolved/` | bearer |
| Alerts | Snooze Alert | Posponer alerta | `POST` | `/api/alerts/alertas/{{alert_id}}/snooze/` | bearer |
| Notifications | List Deliveries | Ver inbox | `GET` | `/api/notifications/deliveries/entregas-notificacion/` | bearer |
| Notifications | Get First Notification Id Helper | Capturar notificacion de prueba | `GET` | `/api/notifications/deliveries/entregas-notificacion/` | bearer |
| Notifications | Mark Delivery Read | Marcar notificacion leida | `POST` | `/api/notifications/deliveries/entregas-notificacion/{{notification_id}}/mark_read/` | bearer |
| Notifications | Mark All Read | Limpiar inbox | `POST` | `/api/notifications/deliveries/entregas-notificacion/mark_all_read/` | bearer |
| Notifications | Delivery Stats | Ver resumen del inbox | `GET` | `/api/notifications/deliveries/entregas-notificacion/stats/` | bearer |
| Realtime | List Signals | Ver feed realtime | `GET` | `/api/realtime/consumers/senales-realtime/` | bearer |
| Realtime | Latest Signal | Polling de ultima senal | `GET` | `/api/realtime/consumers/senales-realtime/latest/` | bearer |
| Realtime | Signal Stats | Ver stats realtime | `GET` | `/api/realtime/consumers/senales-realtime/stats/` | bearer |
| Support | Audit Log | Ver auditoria | `GET` | `/api/support/audit/auditoria/` | bearer |
| Internal | Alerts AI Worker | Worker IA interno | `POST` | `/api/alerts/internal/ai-worker/` | token interno |
| Internal | Internal Account Sync Stub | Sync bancario interno | `POST` | `/internal/integrations/banks/accounts/sync/` | token interno |
| Internal | Internal Account Intelligence Refresh | Refresh inteligencia interno | `POST` | `/internal/integrations/banks/accounts/intelligence/refresh/` | token interno |
