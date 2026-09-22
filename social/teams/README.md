# social.teams

## Responsabilidad

Modela grupos y membresias sociales. No reemplaza el sharing financiero de
`finance.accounts` ni decide permisos sobre el ledger.

## Flujo

1. El usuario crea un equipo y se convierte en owner activo.
2. El owner emite una invitacion desde `social.invitations`.
3. El destinatario acepta de forma explicita.
4. El servicio crea o reactiva la membresia con el rol invitado.
5. Solo miembros activos ven el equipo.
6. Solo el owner administra roles, desactiva miembros o elimina el equipo.

La API de membresias no permite alta directa por `POST`; el camino normal de
ingreso es la invitacion aceptada. `updated_at` participa en las versiones del
BFF mobile para que Flutter detecte cambios incrementales.

## Evolucion

Los equipos pueden ser contexto para presupuestos compartidos, planning y
gastos colaborativos, pero cada bounded context conserva sus propias reglas y
verifica membresia activa antes de operar.
