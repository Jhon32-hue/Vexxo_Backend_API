# social.invitations

## Responsabilidad

Gestiona invitaciones a equipos con token publico, rol, vencimiento,
idempotencia y lifecycle explicito. Las invitaciones para compartir una cuenta
financiera permanecen en `finance.accounts`; ambos contratos son distintos.

## Flujo

1. El owner emite una invitacion para un correo y un rol permitido.
2. El destinatario la consulta con su identidad autenticada.
3. La apertura puede registrarse sin crear permisos.
4. Solo una aceptacion explicita crea o reactiva `social.teams.Membership`.
5. El owner puede revocar mientras siga pendiente o abierta.
6. La entrega al usuario se registra en `notifications.deliveries`.

La API vive en `/api/social/invitations/team-invitations/` y expone acciones
`opened`, `accept` y `revoke`. Listados y acciones se filtran por owner,
remitente, destinatario o correo autenticado.

## Evolucion

El flujo local ya esta conectado a Flutter. Si aparecen consumidores aparte
de notificaciones, se agregara un outbox contextual; no se usaran signals para
ocultar cambios de permisos.
