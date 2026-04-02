# finance.investments

## Que hace

`finance.investments` existe como bounded context reservado para productos o
posiciones de inversion.

## Estado Actual

En esta pasada no encontré una superficie pública o un flujo canónico tan claro
como en `accounts`, `transactions` o `payments`.

El modulo existe en estructura, pero hoy debe leerse como contexto en
preparación.

## Rol Esperado

Cuando se materialice mejor, debería servir para:

- posiciones de inversion
- valorizacion
- rendimiento
- distribucion de portafolio
- integracion con cuentas de inversion y señales de producto

## Relacion Esperada

- `finance.accounts`
  para cuentas tipo inversion
- `finance.fx`
  para multicurrency y valorizacion
- `reports`
  para vistas patrimoniales

## Encaje Con GCP

La evolucion razonable seria:

- OLTP para posiciones y snapshots
- BigQuery para analitica patrimonial o historica
- eventos y proyecciones si se vuelve pieza activa de producto

## Nota

Este README documenta el hueco y la direccion esperada, no una capacidad ya
cerrada al nivel del resto del core.
