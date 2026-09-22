# admin_tools.dashboards

## Que hace

`admin_tools.dashboards` existe para dashboards internos de operacion.

## Rol En El Sistema

Seria el lugar natural para consolidar:

- salud operativa
- volumen de negocio
- colas, fallos o lags
- soporte e indicadores internos

## Valor Operativo

Un dashboard interno no reemplaza la observabilidad tecnica, pero ayuda a
traducir señales del sistema en una vista operable para negocio y soporte.

## Relacion Con Otros Modulos

- `observability`
  metricas y salud tecnica.
- `support.audit`
  trazabilidad funcional.
- `payments`, `accounts`, `notifications`
  dominios que producen senales operativas.

## Estado Actual

La superficie staff-only `GET /api/internal/support/operations/` consolida:

- pendientes, fallos, dead letters y antiguedad por outbox
- estado persistido de scheduler
- estados del worker `documents.ocr`
- entregas de notificacion pendientes/fallidas
- callbacks invalidos, casos abiertos y settlement mismatches de pagos
- contrato de busqueda de logs JSON por `request_id`
- version activa de cifrado, credenciales pendientes de rotacion, bloqueos de
  throttle, eventos criticos y ultimo trabajo de llaves

Cada consulta queda registrada en `support.audit`. Los logs HTTP siguen en
stdout JSON; el dashboard no pretende reemplazar un agregador de logs.
