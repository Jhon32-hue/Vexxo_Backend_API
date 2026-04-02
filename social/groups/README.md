# social.groups

## Que hace

`social.groups` existe como contexto para grupos sociales generales mas amplios
que una sola cuenta o una sola meta.

## Estado Del Codigo

Hoy el modulo esta en scaffold:

- `models.py` vacio
- `views.py` vacio

## Relacion Con Otros Modulos

- `social.teams`
  hoy es el contexto operativo mas cercano a grupos.
- `social.memberships`
  podria modelar pertenencia general.
- `planning.shared_goals`
  podria reutilizar grupos en el futuro.

## Estado Actual

El contexto esta reservado, pero la implementacion visible hoy para pertenencia
y colaboracion general esta mas en `social.teams`.
