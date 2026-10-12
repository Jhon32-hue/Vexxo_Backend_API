# reports.monthly_reports

## Responsabilidad

Materializa un cierre mensual reproducible por `owner + month + currency`.
Solo admite meses terminados en la zona horaria solicitada.

## Contrato

- `POST /api/reports/monthly-closes/`
- `GET /api/reports/monthly-closes/`
- el primer cierre crea version 1
- repetir sin `regenerate` devuelve el cierre vigente
- regenerar exige `reason` y crea una nueva version enlazada por `supersedes`
- nunca se sobrescribe un snapshot anterior

El snapshot incluye cashflow confirmado y el overview de presupuestos del mes.
Las transacciones se filtran por moneda de la cuenta; no se hace conversion FX
implicita.

```json
{
  "month": "2026-08",
  "currency": "COP",
  "timezone": "America/Bogota",
  "regenerate": false,
  "reason": ""
}
```

## Limites

- no existe cierre automatico: es una operacion explicita
- no existe PDF todavia
- la retencion legal definitiva depende de jurisdiccion y politica de negocio

<!-- backend-source-audit:start -->
## Evidencia del codigo y mapa de dependencias

Inventario estatico reproducible del checkout. Describe declaraciones e imports;
no prueba despliegue, permisos efectivos ni que todos los caminos se ejecuten.
Las rutas son locales a su URLConf: el prefijo publico se consulta en
[`api/v1/routers.py`](../../api/v1/routers.py).

- Archivos Python de implementacion: **7** (excluye tests y migraciones).
- Huella SHA-256 del codigo inventariado: `011c076ee7e54b2b36d9b1bcc7e4419b63d79bd7af89b23cf756e72236d2df3b`.
- Familias detectadas: models, services, views.

### Declaraciones de modelos detectadas

- `MonthlyReportClose` en [reports/monthly_reports/models.py](models.py).

### Rutas declaradas

| Patron local | Fuente |
| --- | --- |
| `monthly-closes/` | [reports/monthly_reports/urls.py](urls.py) |

### Diagrama de dependencia estatica

Las flechas representan imports entre paquetes, no eventos ni orden de ejecucion.

```mermaid
flowchart LR
    M["reports.monthly_reports"]
    M --- E["Sin imports absolutos a otros paquetes de dominio detectados"]
```

Flujos transversales: [flujo actualizado](../../docs/BACKEND_CURRENT_FLOW.md).

Regeneracion: `py -3 scripts/audit_backend_docs.py --write`.
Comprobacion de deriva: `py -3 scripts/audit_backend_docs.py --check`.
<!-- backend-source-audit:end -->
