# support.audit

## Que hace

`support.audit` guarda evidencia de acciones sensibles del sistema y de usuario.

Su funcion es:

- registrar quien hizo que
- sobre que entidad
- con que impacto
- con que metadata o diff relevante

## Por Que Existe

En un backend financiero no basta con logs tecnicos.

Hace falta una superficie de auditoria entendible para:

- soporte
- operaciones
- revisiones internas
- trazabilidad de acciones sensibles

## Flujo Principal

1. un bounded context ejecuta una accion critica
2. llama `audit_log(...)`
3. se persiste `AuditLog`
4. soporte o backoffice consulta ese historial via API

## Politica Del Modulo

- la auditoria no debe romper el flujo de negocio
- si falla y `silent=True`, el negocio sigue y el error se registra
- debe capturar modulo, accion, entidad, impacto y metadata suficiente

## Relacion Con Otros Modulos

- `finance.accounts`
  usa auditoria en acciones de lifecycle y sharing
- `payments`
  puede auditar intents, payouts, callbacks manuales o intervenciones operativas
- `identity`
  puede auditar grants, revocaciones y cambios sensibles

## Encaje Con GCP

Esta capa complementa, no reemplaza:

- Cloud Logging
- Cloud Monitoring
- Error Reporting

Diferencia:

- logging = observabilidad tecnica
- audit = trazabilidad funcional de negocio

## Casos De Uso

- quien revoco acceso a una cuenta compartida
- quien forzo recalculo o cambio de estado
- quien aplico un deny explicito de permiso
- que operador intervino un payout o pago en disputa

## Estado Actual

Hoy existe como registro funcional persistente y helper comun `audit_log(...)`.

La arquitectura ya deja listo el camino para:

- enriquecer metadata y diffs
- abrir mejores vistas de backoffice
- correlacionar auditoria con eventos y casos operativos
