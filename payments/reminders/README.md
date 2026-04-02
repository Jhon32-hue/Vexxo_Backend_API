# payments.reminders

## Que hace

`payments.reminders` existe como submodulo para recordatorios relacionados con
pagos.

## Rol En El Producto

Tiene sentido para casos como:

- recordar una factura o servicio
- avisar vencimientos proximos
- reforzar pagos recurrentes o programados

## Flujo Esperado

1. una fecha relevante o regla temporal se aproxima
2. el sistema evalua si corresponde recordar
3. se dispara notificacion, alerta o señal programada
4. el usuario decide pagar, posponer o ignorar

## Relacion Con Otros Modulos

- `payments.scheduled_payments`
  origen natural de muchas fechas o compromisos.
- `notifications`
  canal de entrega.
- `tasks.scheduled`
  ejecucion periodica o programada.

## Encaje Con GCP

Puede apoyarse naturalmente en:

- Cloud Scheduler
- Cloud Tasks
- Cloud Run workers

## Estado Actual

Hoy la subapp aparece instalada en Django, pero no detecte una superficie
funcional rica en esta pasada. Debe leerse como frontera preparada, no como
recordatorio fully wired.
