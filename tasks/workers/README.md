# tasks.workers

## Que hace

`tasks.workers` existe como contexto reservado para definir workers genericos o
su estado operativo.

## Estado Del Codigo

Hoy el app esta en scaffold:

- `models.py` vacio
- sin una superficie worker rica detectada

## Relacion Con Otros Modulos

El sistema ya tiene trabajo de fondo real, pero hoy mucho de eso vive dentro de
los contextos especificos:

- `finance.accounts`
- `payments`
- `alerts`
- `identity.eventing`

Este app todavia no concentra esa operacion.

## Casos De Uso Naturales

- procesadores genericos de cola
- workers de mantenimiento
- ejecucion desacoplada por tipo de trabajo
- monitoreo basico de workers si se materializa mas adelante

## Encaje Con GCP

Cuando madure, puede servir como capa comun para workers desplegados en:

- Cloud Run
- Pub/Sub consumers
- Cloud Tasks handlers

## Estado Actual

El wrapper `run_worker` unifica estos job types:

- `accounts.sync`
- `accounts.intelligence`
- `alerts.ai`
- `transactions.voice`
- `documents.ocr`
- `security.key_rotation`

Los modelos y la logica de cada worker siguen perteneciendo a su bounded
context. `security.key_rotation` es finito/on-demand: reenvuelve DEKs por lotes
y termina cuando ya no hay credenciales pendientes; no requiere un contenedor
permanente.
