# tasks.scheduled

## Que hace

`tasks.scheduled` agrupa trabajo programado o periodico del sistema.

## Archivos Presentes

- `calendar_sync.py`
- `cleanups.py`
- `monthly_reports.py`
- `reminders.py`
- `models.py`

## Rol Esperado

Este subdirectorio es el lugar natural para cosas como:

- limpiezas programadas
- recordatorios
- cierres o reportes mensuales
- sincronizaciones periodicas

## Flujo Esperado

1. un trigger temporal o cron dispara el trabajo
2. el sistema resuelve lock, contexto o ventana temporal
3. se ejecuta el job de negocio o mantenimiento
4. si hace falta, se emiten eventos o se persisten artefactos/resultados

## Estado Del Codigo

En esta pasada no detecte logica consolidada en esos archivos ni modelos
operativos visibles. Debe leerse como una estructura preparada para jobs
cron-like mas que como un scheduler ya cerrado.

## Relacion Con Otros Modulos

- `reports`
  cierres mensuales y snapshots.
- `payments`
  recordatorios o pagos programados.
- `finance.accounts`
  snapshots, cleanups o sync periodico.
- `documents`
  limpiezas de artefactos y expiraciones.

## Encaje Con GCP

Su encaje natural es:

- Cloud Scheduler como trigger
- Cloud Tasks o Cloud Run jobs como ejecucion
- Cloud SQL para estado o locks si hacen falta
