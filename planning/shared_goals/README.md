# planning.shared_goals

## Responsabilidad

Comparte una meta existente con un `social.teams.Team` sin transferir su
ownership. La meta y su verdad financiera conservan un owner; cada aporte
conserva su propio contributor, cuenta y transaccion.

## API

- `GET|POST /api/planning/shared-goals/goals/`
- `PATCH /api/planning/shared-goals/goals/{id}/`
- `POST .../{id}/revoke/`
- `GET .../{id}/projection/`

`contribution_policy=members` permite aportar a miembros activos.
`contribution_policy=managers` limita aportes a owner/accountant. Revocar es
explicito, requiere motivo y no elimina aportes historicos.

## Limites

- usa las membresias e invitaciones existentes de teams
- todavia no hay invitacion exclusiva por meta
- no distribuye ownership contable ni permite usar cuentas de otro miembro
