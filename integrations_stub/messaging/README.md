# integrations_stub.messaging

## Que hace

`integrations_stub.messaging` representa el adapter externo de mensajeria para
codigos temporales de autenticacion y futuros magic links.

No es fuente de verdad. La fuente de verdad sigue siendo:

- `identity.users.UserAuthChallenge`
- `notifications.deliveries.NotificationDelivery`

## Rol En La Arquitectura

- `identity.users` decide que challenge emitir
- `integrations_stub.messaging` decide como intentar entregar el mensaje
- `notifications.deliveries` deja trazabilidad durable del intento

## Local vs cloud

- local/dev:
  - `IDENTITY_MESSAGE_BACKEND=local_stub`
  - el codigo queda solo en trazabilidad local si el flag debug esta activo
- cloud/prod:
  - el backend de mensajeria debe reemplazarse por un adapter real
  - el contrato del challenge no cambia

## Nota

Este stub existe para evitar meter transporte SMS/WhatsApp dentro de
`identity.users`. El bounded context de identidad modela auth; no el proveedor
externo.
