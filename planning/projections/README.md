# planning.projections

## Que hace

`planning.projections` existe como lugar para escenarios y proyecciones
financieras futuras.

Ejemplos conceptuales:

- evolucion estimada de una meta
- cashflow futuro
- simulaciones de ahorro, deuda o inversion

## Estado Del Codigo

Hoy el modulo esta en scaffold:

- `models.py` vacio
- `views.py` vacio
- sin endpoint o calculadora publica detectada

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

No hay implementacion funcional visible hoy. El nombre del contexto anticipa una
evolucion importante del producto, pero todavia no debe confundirse con una
capacidad ya cerrada.
