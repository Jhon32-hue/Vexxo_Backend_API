# planning.shared_goals

## Que hace

`planning.shared_goals` existe para metas compartidas entre varias personas o
colaboradores.

## Estado Del Codigo

Hoy el modulo esta en scaffold:

- `models.py` vacio
- `views.py` vacio
- sin flujos publicos detectados

## Relacion Con Otros Modulos

- `planning.goals`
  base natural de la meta individual.
- `social.teams`
  puede aportar grupo o pertenencia social.
- `finance.accounts`
  ya tiene sharing de cuentas, pero no metas compartidas maduras.

## Rol En El Producto

Este contexto es coherente con una app financiera personal que tambien quiere
abrir colaboracion:

- metas de pareja
- viaje compartido
- ahorro grupal
- objetivos de equipo pequeno

## Encaje Con GCP

Cuando madure, seguira el mismo patron del resto del sistema:

- Cloud Run para CRUD y orchestration
- Cloud SQL para persistencia
- eventos para cambios de estado y notificaciones

## Estado Actual

Todavia es una reserva de dominio. La colaboracion fuerte actual de Vexxo vive
mas en `finance.accounts` y `social.teams`.
