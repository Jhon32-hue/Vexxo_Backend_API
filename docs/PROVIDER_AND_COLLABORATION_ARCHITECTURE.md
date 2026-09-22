# Arquitectura de proveedores y colaboracion

## Objetivo

Permitir que Vexxo agregue bancos, pagos, fuentes de datos y capacidades
colaborativas sin registrar cada feature por entorno ni introducir ramas de
dominio para local y cloud. El codigo funcional es unico; los secretos y
adapters fisicos se inyectan por configuracion.

## Fronteras

| Contexto | Decide | No debe decidir |
| --- | --- | --- |
| `identity` | identidad, sesion, dispositivo, consentimiento y capacidades | movimientos o saldos |
| `integrations` | autorizacion externa, adapters, webhooks y normalizacion | verdad contable |
| `finance.accounts` | ownership, cuenta canonica y estado de sync | autenticacion del proveedor |
| `finance.transactions` | ledger e intake canonico | OAuth o entrega de notificaciones |
| `payments` | intencion, ejecucion externa, webhook y conciliacion | clasificacion final del ledger por side effect |
| `planning` | reglas, proyecciones y acciones programadas | mutaciones ocultas sobre transacciones |
| `alerts` | politicas y alertas derivadas de hechos | reemplazar validaciones de dominio |
| `notifications` | preferencias y entrega al inbox | conceder permisos o ejecutar dinero |
| `social` | grupos, invitaciones y membresias | permisos sobre cuentas sin validar `finance.accounts` |

## Flujo Open Banking

```text
Flutter -> integrations.open_banking -> identity.consents
                                  -> finance.accounts sync/outbox
worker/adaptador -> transactions intake -> finance.transactions ledger
domain events -> alerts/notifications -> polling incremental Flutter
```

La conexion y el consentimiento son sincronos. La importacion es durable y
asincrona. Un webhook firmado solo confirma un hecho externo y agenda trabajo;
no escribe transacciones. El worker traduce al contrato de intake y conserva
idempotencia por proveedor, cuenta, movimiento y corrida.

## Alertas y triggers

No se creara un motor generico de triggers para ocultar reglas. Cada bounded
context emite eventos explicitos mediante su outbox despues del commit. Los
handlers idempotentes convierten esos eventos en alertas, notificaciones o
proyecciones. Los Django signals quedan reservados para comportamiento tecnico
sin decisiones financieras; no gobiernan deudas, pagos, ledger o permisos.

Ejemplos de eventos previstos:

- `integrations.open_banking.connection_attention_required.v1`
- `accounts.sync_succeeded.v1` y `accounts.sync_failed.v1`
- `payments.intent_requires_action.v1`
- `planning.scheduled_action_due.v1`
- `social.team_invitation_accepted.v1`

Se agrega un outbox contextual solo cuando existe un consumidor asincrono o
una entrega que deba sobrevivir al request. No existe un outbox global porque
mezclaria ownership, retencion, retries y semantica de dominios distintos.

## Invitaciones

- Cuenta financiera: `finance.accounts`, porque concede acceso financiero.
- Equipo: `social.invitations`, porque concede membresia social.
- Grupo de planning futuro: debe referenciar una membresia social activa y
  aplicar sus permisos propios; no debe reutilizar silenciosamente permisos de
  cuenta.

Toda invitacion tiene emisor autorizado, destinatario, rol, expiracion,
idempotencia, aceptacion visible y revocacion. Flutter representa permisos
calculados por API (`can_accept`, `can_revoke`) y nunca los infiere.

## Registro de un proveedor nuevo

1. Agregar un descriptor al catalogo de su categoria.
2. Implementar el adapter contra una interfaz del bounded context.
3. Declarar variables requeridas, dejandolas vacias en ejemplos.
4. Implementar firma, deduplicacion y allowlist de webhook.
5. Mapear respuestas al contrato canonico; no persistir payloads completos por
   conveniencia.
6. Exponer estado seguro al frontend, nunca secretos.
7. Agregar observabilidad y documentacion del lifecycle.

No se modifican `run_stack`, Docker slices ni codigo por ambiente por cada
proveedor. Docker y un despliegue futuro solo traducen variables externas a
los nombres canonicos del adapter.

## Secuencia de crecimiento

1. `local_mock` con cuentas y movimientos reproducibles: completado.
2. Elegir un unico agregador Open Banking y construir OAuth/callback real.
3. Cerrar conciliacion de movimientos duplicados, corregidos y eliminados.
4. Aplicar preferencias a todas las notificaciones y alertas de integracion.
5. Terminar un proveedor de pagos con firma y conciliacion end-to-end.
6. Conectar planning a eventos financieros confirmados, no a cache de UI.
7. Agregar panel staff para conexiones, webhooks rechazados y corridas de sync
   sin mostrar secretos ni payload financiero completo.
