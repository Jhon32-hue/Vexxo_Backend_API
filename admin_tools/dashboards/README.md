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

Subapp instalada, pero sin una superficie funcional detallada detectada en esta
pasada.
