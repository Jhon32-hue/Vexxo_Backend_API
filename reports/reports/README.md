# reports.reports

## Que hace

`reports.reports` expone reportes agregados simples sobre el ledger.

Su responsabilidad actual es:

- cashflow
- gastos por categoria
- resumen mensual de presupuestos personales y compartidos

## Rol En El Producto

Este contexto convierte transacciones en lectura agregada para el usuario.

De cara al cliente sirve para:

- ver ingresos, gastos y neto
- entender distribucion de gasto por categoria

## Flujo Principal

1. el API recibe filtros o periodo
2. consulta `finance.transactions`
3. agrega resultados
4. devuelve un resumen listo para la app

## Relacion Con Otros Modulos

- `finance.transactions`
  es la fuente principal de datos
- `finance.categories`
  aporta la dimension por categoria
- `finance.accounts`
  puede complementar vistas futuras por cuenta
- `finance.budgets`
  aporta el resumen mensual de presupuestos:
  - personales por categoria
  - compartidos por equipo
  - con metricas `planned/actual/committed/projected`

## Encaje Con GCP

Hoy estos reportes salen de Cloud SQL y sirven para lecturas operativas simples.

Importante:

- para analitica compleja o dashboards grandes, la evolucion natural es usar
  BigQuery
- este modulo no deberia crecer hacia queries muy pesadas en OLTP

## Estado Actual

Hoy expone tres vistas:

- `CashflowView`
- `GastosPorCategoriaView`
- `BudgetMonthlySummaryView`

Son reportes directos y utiles, pero aun no constituyen una capa analitica
amplia ni un data product separado.
