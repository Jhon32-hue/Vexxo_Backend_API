# notifications

## Que hace

`notifications` es la capa de inbox persistente y entrega funcional dentro de
la app.

No es lo mismo que:

- `alerts`, que modela senales o interpretacion del dominio
- `realtime`, que modela feedback tecnico liviano para polling o UX interactiva

`notifications` existe para que el usuario tenga un historial durable de
mensajes importantes.

## Documento canonico y subdocumentos

Este README es el documento canonico del bounded context `notifications`.

Subdocumentos derivados:

- [deliveries/README.md](https://gitlab.com/vexxo-sas/vexxo_backend_api/-/blob/development/notifications/deliveries/README.md)
  inbox persistente y semantica de `NotificationDelivery`
- [listeners/README.md](https://gitlab.com/vexxo-sas/vexxo_backend_api/-/blob/development/notifications/listeners/README.md)
  materializacion de inbox desde eventos del dominio
- [preferences/README.md](https://gitlab.com/vexxo-sas/vexxo_backend_api/-/blob/development/notifications/preferences/README.md)
  configuracion activa por canal y marketing/newsletter
- [templates/README.md](https://gitlab.com/vexxo-sas/vexxo_backend_api/-/blob/development/notifications/templates/README.md)
  renderizado y mensajes reutilizables

Regla editorial:

- este README explica `notifications` como modulo
- los subREADME explican ownership puntual por capa

## Componentes Principales

- `deliveries`
  guarda la notificacion persistente visible en la app
- `listeners`
  escucha eventos de dominio y crea entregas
- `preferences`
  preferencias activas del usuario para inbox, push, correo y newsletter
- `templates`
  punto natural para mensajes reutilizables y renderizado

## Por Que Existe

El usuario necesita un historial durable de mensajes importantes aunque no
este conectado en tiempo real.

Este modulo evita depender solo de:

- logs
- alerts tecnicas
- senales efimeras de realtime

## Vista visual

```mermaid
classDiagram
    class NotificationDelivery {
        +notification_key
        +category
        +priority
        +template_version
        +action_path
        +channel
        +status
        +event_type
        +source
        +title
        +message
        +dedupe_key
        +delivered_at
        +read_at
    }

    class DomainEvent {
        +event_type
        +source
        +payload
    }

    DomainEvent --> NotificationDelivery : materializes_when_relevant
```

## Flujo General

1. un bounded context emite un evento fuerte
2. `notifications.listeners` decide si ese evento amerita inbox
3. `notifications.templates.catalog` resuelve identidad, categoria, prioridad,
   copy, payload permitido y deeplink
4. se crea `NotificationDelivery`
5. si el canal es `email`, el futuro worker durable usa la misma definicion y
   marca `delivered` o `failed`
6. mobile/web consume inbox o estado por API
7. el usuario marca como leido y puede navegar a la accion relacionada

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
- la deduplicacion usa el ID estable del outbox: evita duplicar reintentos sin
  silenciar acciones futuras sobre el mismo agregado
- la UI puede mezclar inbox con realtime, pero la fuente durable es
  `NotificationDelivery`

## Estado Actual

Hoy el enfoque principal es inbox in-app persistente.

El catalogo v1 cubre lifecycle, seguridad, cuentas, transacciones, presupuestos,
gastos compartidos, pagos, pagos programados, deudas, metas, alertas y OCR. No
materializa cada escritura tecnica: una accion entra al inbox cuando aporta
confirmacion, requiere atencion o cambia una obligacion. El resto permanece en
eventos, auditoria y logs para evitar fatiga de notificaciones.

`in_app_enabled=false` silencia eventos opcionales. Los avisos de seguridad de
cuenta y dispositivos se conservan como obligatorios para proteger al usuario.

Ya existe ademas:

- trazabilidad de correos lifecycle y reset de password via `NotificationDelivery(channel=email)`
- trazabilidad de recovery/step-up mobile via `NotificationDelivery(channel=system, payload.transport=sms|whatsapp)`
- preferencias de usuario por canal y newsletter

La arquitectura sigue dejando abierto el camino para:

- push provider real
- templates mas ricos
- reglas mas finas por evento

La API acepta `created_after=<ISO-8601>` para polling incremental. Flutter solo
consulta mientras el inbox esta visible y mantiene el inbox persistente como
fuente de verdad; no se requieren WebSockets para la escala local inicial.
