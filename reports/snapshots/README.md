# reports.snapshots

## Que hace

`reports.snapshots` existe como contexto para snapshots persistidos de
reporting.

## Estado Del Codigo

El modulo esta operativo. Persiste snapshots inmutables con periodo, moneda,
zona horaria, `as_of`, version, hash canonico y lineage de regeneracion.

## Por Que Existe

Los snapshots sirven para separar:

- calculo costoso o agregacion historica
- lectura rapida para mobile o soporte

Eso encaja con una arquitectura donde los requests web deben ser ligeros y
parte del trabajo se mueve a jobs o proyecciones.

## Relacion Con Otros Modulos

- `reports.reports`
  lecturas agregadas basadas en ledger.
- `reports.monthly_reports`
  posible consumidor o publicador de snapshots.
- `common` e `identity.eventing`
  patron general de read models del sistema.

## Encaje Con GCP

Cuando se materialice:

- Cloud Run workers pueden construir snapshots
- Cloud SQL o BigQuery pueden alojar resultados segun el caso
- Scheduler puede disparar cierres periodicos

## Estado Actual

`POST /api/reports/snapshots/` exige `Idempotency-Key`. Los tipos activos son
`cashflow`, `expenses_by_category` y `monthly_close`, siempre sobre ledger
autorizado. Una regeneracion nunca modifica el snapshot anterior: crea una
nueva version y conserva `supersedes` y el motivo.
