# social.invitations

## Que hace

`social.invitations` existe como contexto para invitaciones sociales generales.

## Importante

Las invitaciones operativas que hoy si existen y estan endurecidas en el
backend viven principalmente en `finance.accounts` para sharing financiero.

## Estado Del Codigo

Este modulo esta en scaffold:

- `models.py` vacio
- `views.py` vacio

## Relacion Con Otros Modulos

- `finance.accounts`
  invitaciones reales a membresias de cuenta.
- `social.teams`
  podria requerir invitaciones de equipo si madura.
- `notifications`
  canal natural de entrega.

## Estado Actual

No documentar como feature activa. El flujo robusto de invitaciones actual es
el de `finance.accounts`.
