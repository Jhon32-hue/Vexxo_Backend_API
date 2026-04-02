# social.chat

## Que hace

`social.chat` existe como contexto para mensajeria o conversacion social
alrededor de experiencias financieras compartidas.

## Estado Del Codigo

Hoy esta en scaffold:

- `models.py` vacio
- `views.py` vacio

## Relacion Con Otros Modulos

- `social.teams`
  pertenencia y grupo base.
- `social.shared_expenses`
  un chat podria vivir alrededor de un gasto compartido.
- `notifications` y `realtime`
  transporte natural de mensajes o avisos.

## Encaje Con El Negocio

El chat no es core contable, pero si puede reducir friccion social en:

- invitaciones
- aclaracion de gastos
- coordinacion de metas o grupos

## Estado Actual

Contexto reservado; no hay feature visible cerrada hoy.
