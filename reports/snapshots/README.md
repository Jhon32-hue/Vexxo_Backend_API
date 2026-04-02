# reports.snapshots

## Que hace

`reports.snapshots` existe como contexto para snapshots persistidos de
reporting.

## Estado Del Codigo

Hoy el modulo esta en scaffold:

- `models.py` vacio
- `views.py` vacio

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

Contexto reservado; aun no hay proyeccion o snapshot formal visible aqui.
