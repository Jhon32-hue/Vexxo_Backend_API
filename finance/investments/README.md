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

<!-- backend-source-audit:start -->
## Evidencia del codigo y mapa de dependencias

Inventario estatico reproducible del checkout. Describe declaraciones e imports;
no prueba despliegue, permisos efectivos ni que todos los caminos se ejecuten.
Las rutas son locales a su URLConf: el prefijo publico se consulta en
[`api/v1/routers.py`](../../api/v1/routers.py).

- Archivos Python de implementacion: **12** (excluye tests y migraciones).
- Huella SHA-256 del codigo inventariado: `ca5d92b85714513b3434b8d51c094284ed70218d5b4568746ddf65ab11b29c4a`.
- Familias detectadas: models, serializers, views.

### Declaraciones de modelos detectadas

- `Asset` en [finance/investments/Models/asset.py](Models/asset.py).
- `InvestmentAccount` en [finance/investments/Models/account.py](Models/account.py).
- `Position` en [finance/investments/Models/position.py](Models/position.py).
- `PriceHistory` en [finance/investments/Models/price.py](Models/price.py).
- `Trade` en [finance/investments/Models/trade.py](Models/trade.py).

No se detectan declaraciones `path`/`re_path` propias en este alcance.
Esto no implica que el modulo carezca de consumidores internos.

### Diagrama de dependencia estatica

Las flechas representan imports entre paquetes, no eventos ni orden de ejecucion.

```mermaid
flowchart LR
    M["finance.investments"]
    M --- E["Sin imports absolutos a otros paquetes de dominio detectados"]
```

Flujos transversales: [flujo actualizado](../../docs/BACKEND_CURRENT_FLOW.md).

Regeneracion: `py -3 scripts/audit_backend_docs.py --write`.
Comprobacion de deriva: `py -3 scripts/audit_backend_docs.py --check`.
<!-- backend-source-audit:end -->
