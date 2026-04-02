# notifications

## Que hace

`notifications` es la capa de inbox persistente y entrega funcional dentro de
la app.

No es lo mismo que:

- `alerts`, que modela senales o interpretacion del dominio
- `realtime`, que modela feedback tecnico liviano para polling o UX interactiva

`notifications` existe para que el usuario tenga un historial durable de
mensajes importantes.

## Componentes Principales

- `deliveries`
  guarda la notificacion persistente visible en la app
- `listeners`
  escucha eventos de dominio y crea entregas
- `preferences`
  punto natural para politicas de usuario por canal
- `templates`
  punto natural para mensajes reutilizables y renderizado

## Por Que Existe

El usuario necesita un historial durable de mensajes importantes aunque no
este conectado en tiempo real.

Este modulo evita depender solo de:

- logs
- alerts tecnicas
- senales efimeras de realtime

## Flujo General

1. un bounded context emite un evento fuerte
2. `notifications.listeners` decide si ese evento amerita inbox
3. se crea `NotificationDelivery`
4. mobile/web consume el inbox por API
5. el usuario marca como leido o revisa el detalle

## Casos De Uso

- invitacion a cuenta compartida
- invitacion aceptada
- acceso revocado
- sync exitoso o evento importante de operacion
- futuros pagos, disputas o acciones de soporte

## Relacion Con Otros Modulos

- `common.domain_events`: origen del bus compartido
- `finance.accounts`: hoy es uno de los productores principales
- `payments`: futuro productor natural de eventos hacia inbox
- `alerts`: puede complementar o disparar notificaciones funcionales
- `realtime`: complementa UX inmediata, pero no reemplaza el inbox

## Encaje Con GCP

Este modulo puede operar asi:

- API Gateway / Cloud Run exponen inbox al usuario
- listeners locales o consumidores externos materializan `deliveries`
- Pub/Sub puede servir para escalar consumo de eventos a otros servicios
- Cloud SQL mantiene el inbox persistente

El inbox no debe depender de sockets persistentes; debe ser durable y consultable.

## Politicas Del Modulo

- solo mensajes con valor real deben entrar al inbox
- el inbox no reemplaza trazabilidad operativa ni audit log
- la deduplicacion debe evitar spam por reintentos del bus
- la UI puede mezclar inbox con realtime, pero la fuente durable es
  `NotificationDelivery`

## Estado Actual

Hoy el enfoque principal es inbox in-app persistente.

La arquitectura ya deja abierto el camino para:

- email
- push
- templates mas ricos
- preferencias por canal
