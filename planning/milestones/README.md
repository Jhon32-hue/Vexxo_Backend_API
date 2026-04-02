# planning.milestones

## Que hace

`planning.milestones` existe como contexto para hitos intermedios dentro de un
proceso de planning financiero.

Ejemplos conceptuales:

- pasos dentro de una meta
- puntos de seguimiento
- checkpoints de progreso

## Estado Del Codigo

Hoy el modulo esta en scaffold:

- `models.py` vacio
- `views.py` vacio
- sin API o servicios detectados

## Relacion Con Otros Modulos

- `planning.goals`
  ya modela metas como el contexto mas visible de planning.
- `planning.projections`
  puede aportar escenarios futuros.
- `planning.shared_goals`
  podria abrir colaboracion sobre objetivos.

## Encaje Con El Negocio

La idea encaja con el core de Vexxo porque el producto no solo observa dinero;
tambien deberia ayudar a decidir y planear. Los hitos son una forma natural de
convertir una meta grande en pasos comprensibles.

## Encaje Con GCP

Cuando madure, este contexto probablemente sera una capa CRUD y de proyeccion
sobre Cloud SQL, con derivaciones async por eventos o workers.

## Estado Actual

No hay logica operativa visible hoy. Debe leerse como un contexto reservado.
