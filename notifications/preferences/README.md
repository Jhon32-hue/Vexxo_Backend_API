# notifications.preferences

## Que hace

`notifications.preferences` existe como lugar natural para preferencias de
entrega del usuario:

- canales habilitados
- opt-in u opt-out
- reglas de silencio
- granularidad por tipo de notificacion

## Estado Del Codigo

Hoy el modulo esta en scaffold:

- `models.py` vacio
- `views.py` vacio
- sin endpoints o servicios publicos detectados

## Rol En El Producto

Aunque el modulo aun no esta materializado, su responsabilidad es importante.
Vexxo necesita distinguir entre:

- notificaciones que el sistema puede generar
- notificaciones que realmente quiere recibir el usuario
- canal adecuado:
  - in-app
  - push
  - email
  - system

## Relacion Con Otros Modulos

- `notifications.deliveries`
  persiste la entrega o inbox durable.
- `notifications.listeners`
  transforma eventos de dominio en mensajes.
- `realtime`
  puede complementar la experiencia interactiva.
- `identity.users`
  aporta ownership, plan y contexto de producto.

## Encaje Con GCP

Cuando este modulo madure, encajara con:

- Cloud Run para API de preferencias
- Cloud SQL para persistencia
- Pub/Sub o Cloud Tasks para aplicar cambios de forma desacoplada
- servicios de push/email externos desde workers o adapters

## Estado Actual

No conviene documentarlo como feature cerrada hoy. Es un contexto reservado y
coherente con la arquitectura, pero la logica operativa visible sigue viviendo
en `notifications.listeners` y `notifications.deliveries`.
