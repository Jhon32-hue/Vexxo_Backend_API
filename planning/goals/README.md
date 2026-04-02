# planning.goals

## Que hace

`planning.goals` modela metas financieras del usuario.

Su responsabilidad actual es:

- CRUD de metas (`Goal`)

## Rol En El Producto

Este contexto sostiene la parte aspiracional del producto:

- ahorrar para una meta
- seguir progreso hacia un objetivo
- conectar decisiones diarias con resultados futuros

## Flujo Principal

1. el usuario crea una meta
2. la app consulta metas ordenadas por `target_date`
3. otros contextos pueden usar esa informacion para alertas, reportes o
   recomendaciones futuras

## Relacion Con Otros Modulos

- `finance.transactions`
  puede contribuir al progreso de la meta
- `finance.accounts`
  aporta saldos y superficie financiera relevante
- `alerts`
  puede avisar desviaciones o hitos

## Encaje Con GCP

Hoy es un modulo CRUD liviano sobre Cloud SQL.

La evolucion natural es sumar:

- proyecciones
- reglas de avance
- eventos de progreso

sin cambiar su naturaleza de planning.

## Estado Actual

Hoy expone `MetaViewSet` sobre `Goal`.

Es una superficie sencilla, pero es un dominio importante para producto aunque
todavia no tenga automatizacion fuerte alrededor.
