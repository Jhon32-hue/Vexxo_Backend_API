# identity.eventing

## Que hace

Outbox operativo y read models derivados del bounded context de identidad.

Su trabajo es:

- persistir eventos `users.*`, `permissions.*`, `consents.*`, `sessions.*`
- desacoplar escritura transaccional de publicacion al bus
- alojar la proyeccion materializada de uso de producto

## Flujo actual

1. `identity.users.services.event_service.publish_user_event_after_commit()`
   construye el evento y lo encola en `IdentityDomainEventOutbox`.
2. El request web termina sin publicar directamente.
3. Un worker/cron ejecuta:

`python manage.py identity_publish_outbox`

4. Ese worker publica los eventos pendientes/fallidos al bus comun.

## Read models del modulo

### `UserProductUsageProjection`

Snapshot operativo de uso por usuario que mobile/web consulta sin golpear
OLTP en caliente.

### `UserProductUsageProjectionEvent`

Checkpoint persistente de eventos ya aplicados a la proyeccion.

Sirve para:

- evitar dobles aplicaciones de deltas cuando un worker reintenta
- endurecer la evolucion hacia un proyector 100% incremental
- dejar trazabilidad de que `event_key` actualizo el snapshot

No es cache volatil. Es parte de la capa de lectura del producto.

## Relacion con otros modulos

- `common.domain_events`: bus de dominio compartido
- `identity.users`: productor principal de eventos y consumidor de la proyeccion
- `finance.accounts`: emite muchos de los eventos que actualizan usage
- `alerts.alerts`: alimenta uso de IA
- `payments.payment_intents`: alimenta volumen y conteo de pagos
- `payments.payment_intents`: alimenta tambien volumen diario y mensual de
  payouts/dispersions

## Esqueleto/futuro

La direccion objetivo es acercarlo aun mas al outbox de `accounts`:

- retries con backoff formal
- dead-letter operativa
- workers dedicados en Cloud Run / Cloud Tasks / Pub/Sub
- trazabilidad mas rica por publisher

Hoy ya esta fuera del request path; lo siguiente es endurecer la operacion,
no cambiar el contrato.
