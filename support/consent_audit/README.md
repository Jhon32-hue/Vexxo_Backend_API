# support.consent_audit

## Que hace

`support.consent_audit` existe para apoyar trazabilidad y soporte alrededor de
consentimientos.

## Rol En El Sistema

Es un complemento natural de:

- `identity.consents`
  que resuelve consentimiento operativo/legal
- `support.audit`
  que resuelve auditoria funcional general

Aqui tendria sentido exponer vistas especializadas para investigar:

- cuando se otorgo un consentimiento
- cuando se revoco
- que teardown operativo se disparo

## Por Que Importa

En un producto financiero, consentimiento y teardown no son solo detalles
tecnicos. Tambien sostienen cumplimiento, soporte y confianza del usuario.

## Encaje Con GCP

Puede apoyarse en logs, auditoria persistida y read models internos operados
desde Cloud Run y Cloud SQL.

## Estado Actual

La subapp esta instalada, pero no detecte una superficie funcional rica en esta
pasada.
