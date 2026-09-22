# planning.projections

## Que hace

`planning.projections` existe como lugar para escenarios y proyecciones
financieras futuras.

Ejemplos conceptuales:

- evolucion estimada de una meta
- cashflow futuro
- simulaciones de ahorro, deuda o inversion

## Estado Del Codigo

El paquete permanece reservado para escenarios multi-dominio. La proyeccion
operativa inicial de metas vive en `planning.goals` para mantener juntas sus
reglas, permisos y supuestos.

## Relacion Con Otros Modulos

- `planning.goals`
  metas sobre las que pueden construirse proyecciones.
- `reports.reports` y `reports.summaries`
  consumen pasado y presente; este modulo apunta a futuro.
- `alerts`
  podria usar proyecciones para alertas inteligentes.

## Rol En El Producto

Esto toca directamente el loop de Vexxo:

- observar
- interpretar
- decidir

Las proyecciones son una pieza natural del paso de interpretar a decidir.

## Encaje Con GCP

Cuando se materialice, podria apoyarse en:

- Cloud Run para calculo y API
- BigQuery o pipelines analiticos para features
- Gemini o modelos auxiliares para explicacion

## Estado Actual

`GET /api/planning/goals/metas/<id>/projection/` calcula velocidad historica,
fecha estimada y aporte mensual requerido. Es determinista y no modifica el
ledger. Este paquete no expone una segunda API hasta que existan escenarios
transversales versionados.
