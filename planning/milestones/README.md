# planning.milestones

## Que hace

`planning.milestones` existe como contexto para hitos intermedios dentro de un
proceso de planning financiero.

Ejemplos conceptuales:

- pasos dentro de una meta
- puntos de seguimiento
- checkpoints de progreso

## Estado Del Codigo

El paquete permanece reservado para una futura separacion de bounded context.
La capacidad operativa actual vive deliberadamente en `planning.goals` como
`GoalMilestone`, porque el hito comparte aggregate, lock y outbox con la meta.

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

La API activa es `POST /api/planning/goals/milestones/`. No se duplica aqui
para evitar dos fuentes de verdad. Una separacion futura requerira migracion de
datos, contrato versionado y compatibilidad explicita.
