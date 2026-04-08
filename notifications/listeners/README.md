# notifications.listeners

## Que hace

`notifications.listeners` convierte eventos del dominio en notificaciones
persistentes para el usuario.

No reemplaza a `alerts` ni a `realtime`. Su foco es inbox y comunicacion
durable.

## Alcance documental

Este README es derivado del documento canonico del modulo:

- [notifications/README.md](/c:/Users/Alamb/Documents/Vexxo_Backend_API/notifications/README.md)

Su foco es la materializacion de inbox desde eventos; no explica todo el
bounded context `notifications`.

## Estado Actual Real

Este modulo si tiene una pieza operativa clara:

- `event_handlers.py`

Los modelos y vistas del app siguen en scaffold, pero los listeners ya
persisten entregas a traves de `notifications.deliveries`.

## Flujo Principal

1. ocurre un evento de dominio en `accounts`
2. un subscriber en `notifications.listeners.event_handlers` lo recibe
3. se decide usuario destino, titulo y mensaje
4. se construye `dedupe_key`
5. se crea `NotificationDelivery`

Eventos observados hoy:

- `accounts.membership.invited`
- `accounts.membership.accepted`
- `accounts.membership.revoked`
- `accounts.primary.changed`
- `accounts.archived`
- `accounts.sync.succeeded`

## Casos De Uso

### Invitacion a cuenta compartida

- se emite evento de invitacion
- el listener crea un item de inbox para el usuario invitado

### Aceptacion de colaborador

- se emite evento de aceptacion
- el owner recibe confirmacion durable

### Sincronizacion exitosa

- el usuario recibe feedback de una cuenta sincronizada

## Relacion Con Otros Modulos

- `common.domain_events`
  fuente de suscripcion y bus compartido.
- `notifications.deliveries`
  almacenamiento durable del mensaje.
- `finance.accounts`
  principal contexto emisor observado hoy.
- `realtime`
  puede complementar con feedback interactivo, pero no reemplaza el inbox.

## Encaje Con GCP

Hoy estos listeners pueden vivir en el proceso del backend o en workers, pero
la evolucion natural en GCP es:

- eventos de dominio publicados por outbox
- Pub/Sub o Cloud Tasks para fan-out externo
- Cloud Run workers para entrega por canal
- persistencia durable en Cloud SQL

## Estado Actual

El valor real del modulo ya existe en `event_handlers.py`.
Lo que aun no aparece aqui es un subdominio rico de configuracion o modelos
propios; esa parte sigue apoyandose en `notifications.deliveries`.
