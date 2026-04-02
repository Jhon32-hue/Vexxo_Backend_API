# scripts

## Que hace

`scripts` contiene utilidades operativas y de mantenimiento fuera del request
path normal del backend.

## Archivos Presentes

- `backfill_events.py`
- `bootstrap.py`
- `generate_reports.py`
- `migrate_data.py`

## Estado Del Codigo

En esta pasada no detecte implementacion funcional visible dentro de esos
archivos. Por eso conviene documentarlos por su rol estructural y no como
herramientas cerradas.

## Rol En El Sistema

Este directorio es el lugar correcto para:

- bootstrap local o de entorno
- backfills de eventos o proyecciones
- migraciones de datos extraordinarias
- generacion puntual de reportes o artefactos

## Criterio De Uso

Los scripts aqui no deben reemplazar logica de aplicacion estable. Su espacio es
para:

- operaciones puntuales
- bootstrap
- mantenimientos o migraciones controladas
- backfills excepcionales

## Relacion Con Otros Modulos

- `common` e `identity.eventing`
  candidatos naturales para backfills.
- `reports`
  generacion extraordinaria de reportes.
- `finance` y `payments`
  migraciones o normalizacion de datos historicos.

## Encaje Con GCP

Cuando estas piezas se formalizan en cloud, suelen migrar a:

- Cloud Run jobs
- scripts internos de CI/CD
- tareas ad-hoc operadas desde pipelines

## Estado Actual

Directorio util y bien ubicado, pero sus scripts no deben asumirse como
herramientas listas de produccion sin revisar su contenido concreto.
