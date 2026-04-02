# alerts.triggers

## Que hace

`alerts.triggers` existe como lugar natural para modelar condiciones o
disparadores de alertas separados de:

- la alerta generada (`alerts.alerts`)
- la regla configurable (`alerts.rules`)

## Estado Del Codigo

Hoy el modulo esta en scaffold:

- `models.py` vacio
- `views.py` vacio
- sin motor de triggers publico detectado

## Rol En El Producto

La separacion conceptual sigue siendo util:

- `rules` describe configuracion del usuario
- `triggers` describiria la condicion evaluable
- `alerts` materializaria el resultado observable

Eso encaja con una app financiera que quiere pasar de alertas simples a
automatizacion y deteccion mas rica.

## Relacion Con Otros Modulos

- `alerts.rules`
  reglas configurables del usuario.
- `alerts.alerts`
  la alerta final visible para el usuario.
- `finance.transactions`, `finance.accounts`, `payments`
  posibles fuentes de eventos para futuros triggers.

## Encaje Con GCP

Cuando se materialice, este modulo encajara bien con:

- Cloud Tasks o Pub/Sub para evaluar triggers desacoplados
- Cloud Run workers para reglas pesadas o por lotes
- Cloud SQL para definicion y estado

## Estado Actual

Hoy la idea del modulo es correcta, pero no hay una implementacion operativa
documentable mas alla del scaffold.
