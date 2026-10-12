# social.memberships

## Que hace

`social.memberships` existe como contexto para membresias sociales generales,
distintas de las membresias financieras de `finance.accounts`.

## Estado Del Codigo

Hoy esta en scaffold:

- `models.py` vacio
- `views.py` vacio

## Relacion Con Otros Modulos

- `social.teams`
  hoy ya implementa una membresia concreta por equipo.
- `finance.accounts`
  tiene membresias operativas fuertes para sharing financiero.

## Estado Actual

Este contexto aun no tiene una implementacion visible propia. La nocion de
membresia activa hoy se resuelve en otros modulos mas especificos.

<!-- backend-source-audit:start -->
## Evidencia del codigo y mapa de dependencias

Inventario estatico reproducible del checkout. Describe declaraciones e imports;
no prueba despliegue, permisos efectivos ni que todos los caminos se ejecuten.
Las rutas son locales a su URLConf: el prefijo publico se consulta en
[`api/v1/routers.py`](../../api/v1/routers.py).

- Archivos Python de implementacion: **5** (excluye tests y migraciones).
- Huella SHA-256 del codigo inventariado: `3ff9907472de1583a4f21d7602c4e10d2cda04fe83674a28592d67f30dc5850b`.
- Familias detectadas: models, views.

No se detectan declaraciones `path`/`re_path` propias en este alcance.
Esto no implica que el modulo carezca de consumidores internos.

### Diagrama de dependencia estatica

Las flechas representan imports entre paquetes, no eventos ni orden de ejecucion.

```mermaid
flowchart LR
    M["social.memberships"]
    M --- E["Sin imports absolutos a otros paquetes de dominio detectados"]
```

Flujos transversales: [flujo actualizado](../../docs/BACKEND_CURRENT_FLOW.md).

Regeneracion: `py -3 scripts/audit_backend_docs.py --write`.
Comprobacion de deriva: `py -3 scripts/audit_backend_docs.py --check`.
<!-- backend-source-audit:end -->
