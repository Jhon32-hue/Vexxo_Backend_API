# social.shared_expenses

## Que hace

`social.shared_expenses` existe como contexto para gastos compartidos entre
personas o grupos.

## Estado Del Codigo

Hoy esta en scaffold:

- `models.py` vacio
- `views.py` vacio

## Por Que Existe

Es un caso de uso natural para una app financiera personal:

- viaje con amigos
- pareja o roommates
- gastos de equipo pequeno

## Relacion Con Otros Modulos

- `contacts`
  contactos financieros del usuario.
- `social.teams`
  grupo compartido.
- `finance.transactions`
  ledger y participantes de transaccion.
- `documents`
  comprobantes y soportes.

## Estado Actual

El contexto aun no esta materializado como producto completo. Hoy Vexxo ya
tiene piezas relacionadas, pero no una superficie cerrada de gastos
compartidos en este modulo.
