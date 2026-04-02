# notifications.deliveries

## Que hace

`notifications.deliveries` es el inbox persistente de la app.

Su responsabilidad es:

- almacenar entregas visibles por el usuario
- deduplicar mensajes cuando el bus reintenta
- permitir lectura, listado y marcado como leido

## Flujo Principal

1. un listener decide crear una notificacion
2. `create_notification_delivery()` persiste la entrega
3. mobile/web consulta el inbox por API
4. el usuario marca una o varias entregas como leidas

## Diferencia Frente a Otras Capas

- `alerts`
  modela la senal o interpretacion
- `notifications.deliveries`
  materializa un mensaje durable para el usuario
- `realtime.consumers`
  refleja una senal tecnica y liviana para interaccion

## Relacion Con Otros Modulos

- `notifications.listeners`
  productor principal de deliveries
- `finance.accounts`
  hoy es productor importante via eventos de membresias, sync y lifecycle
- `payments`
  sera productor natural de notificaciones operativas y de pago

## Encaje Con GCP

Es una pieza simple y robusta para Cloud SQL + Cloud Run:

- almacenamiento durable en OLTP
- API de lectura desde BFF
- posibilidad futura de fan-out a otros canales sin cambiar la semantica base

## Politicas Del Modulo

- el inbox debe ser durable
- la deduplicacion debe proteger frente a retries del bus
- el estado `read` no debe perder trazabilidad de `delivered`
- la UI no debe confundir inbox con realtime efimero

## Estado Actual

Hoy el foco es canal `in_app`, pero el modelo ya deja espacio para `email`,
`push` y `system`.

## Casos De Uso

- “te compartieron una cuenta”
- “tu acceso fue revocado”
- “la sincronizacion se completo”
- “tu pago requiere accion”
- “una dispersion fallo”
