"""Reserved module. Active HTTP routing lives in realtime.consumers.urls.

# realtime

## Que hace

`realtime` guarda senales tecnicas livianas para feedback rapido de la app.

No es un inbox funcional ni un stream de negocio duradero. Es una capa de UX y
observabilidad de bajo costo.

## Estado Actual

Hoy el modulo funciona principalmente con `RealtimeSignal` persistido.

Eso permite:

- polling barato desde mobile/web
- inspeccion operativa por soporte
- desacoplar feedback interactivo del bus de dominio fuerte

## Por Que Existe

La app necesita feedback rapido, pero no todo merece:

- inbox durable
- notificacion funcional
- dependencia directa del bus fuerte

`realtime` existe para cubrir ese espacio intermedio.

## Diferencia Frente a Notifications

- `notifications`:
  mensaje funcional y durable para el usuario
- `realtime`:
  señal tecnica corta para superficies interactivas

Ejemplo:

- `payments.intent.processing` puede reflejarse como `RealtimeSignal`
- un problema serio o una accion importante puede terminar tambien en inbox

## Flujo General

1. un bounded context emite evento fuerte
2. listener local o servicio especifico traduce eso a `RealtimeSignal`
3. mobile/web consulta `realtime/consumers`
4. la UI actualiza estado o badges sin tener que esperar procesamiento largo

## Relacion Con Otros Modulos

- `finance.accounts`: publica cambios de balance, sync y membresias
- `payments.payment_intents`: publica progreso de intents y payouts
- `notifications`: cubre la capa durable que `realtime` no pretende cubrir

## Encaje Con GCP

La estrategia esperada es:

- hoy: polling desde API Gateway/BFF contra Cloud SQL
- mañana: SSE, WebSocket gateway o Redis/Memorystore para presencia y baja latencia

Este modulo ya deja la semantica lista para migrar a una capa mas viva sin
romper el contrato de la app.

## Futuro Natural

Los archivos vacios actuales (`presence.py`, `redis_channels.py`, `routing.py`,
`unread_counters.py`) son placeholders del camino cloud-native:

- presencia
- fan-out por canales
- gateways WebSocket/SSE
- contadores en memoria o Redis

La fuente semantica actual sigue siendo `RealtimeSignal`.

## Politicas Del Modulo

- una senal realtime debe ser barata y simple
- no debe cargar logica de negocio rica
- no debe reemplazar outbox ni auditoria
- debe poder migrar a gateways vivos sin romper el contrato de lectura
"""
