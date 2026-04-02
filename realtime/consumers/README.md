# realtime.consumers

## Que hace

`realtime.consumers` persiste `RealtimeSignal`, una capa liviana de feedback
interactivo para mobile/web.

No pretende ser:

- el bus de dominio
- el inbox durable
- un stream garantizado de negocio

Su objetivo es dar a la UI una superficie barata para polling y depuracion.

## Flujo Principal

1. un bounded context produce un cambio relevante
2. un listener o servicio lo traduce a `RealtimeSignal`
3. mobile/web consulta la API de senales
4. la UI actualiza estado, badges o progresos sin esperar procesos mas pesados

## Campos Semanticos

Una `RealtimeSignal` suele guardar:

- `channel`
- `event`
- `aggregate_type`
- `aggregate_id`
- `payload`

Eso permite filtrar por recurso y por tipo de evento sin depender del bus
interno completo.

## Relacion Con Otros Modulos

- `finance.accounts`
  publica cambios de balance, sync y memberships
- `payments.payment_intents`
  publica progreso de intents y payouts
- `notifications`
  cubre lo durable que `RealtimeSignal` no quiere cubrir

## Encaje Con GCP

Hoy funciona bien con Cloud SQL + polling.

Mañana puede evolucionar a:

- SSE
- WebSocket gateway
- Redis/Memorystore
- canales por usuario o aggregate

sin cambiar la semantica de `event`, `channel` y `aggregate`.

## Casos De Uso

- estado de un pago: `processing -> requires_action -> succeeded`
- cambio rapido de saldo o sync de cuenta
- señal tecnica para refrescar una vista especifica

## Politicas Del Modulo

- una señal debe ser pequeña y facil de interpretar
- no debe reemplazar el feed de notificaciones ni el audit log
- debe estar alineada con eventos fuertes, no inventar semantica paralela

## Estado Actual

Hoy se expone por API de lectura y sirve para polling.

La evolucion futura puede mover el transporte, pero no deberia romper la forma
de `channel`, `event`, `aggregate_type` y `aggregate_id`.
