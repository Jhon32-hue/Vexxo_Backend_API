# social.memberships

## Que hace

`social.memberships` existe como contexto para membresias sociales generales,
distintas de las membresias financieras de `finance.accounts`.

## Estado Del Codigo

Hoy esta en scaffold:

- `models.py` vacio
- `views.py` vacio

## Relacion Con Otros Modulos

- `social.teams`
  hoy ya implementa una membresia concreta por equipo.
- `finance.accounts`
  tiene membresias operativas fuertes para sharing financiero.

## Estado Actual

Este contexto aun no tiene una implementacion visible propia. La nocion de
membresia activa hoy se resuelve en otros modulos mas especificos.
