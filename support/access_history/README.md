# support.access_history

## Que hace

`support.access_history` existe como submodulo de soporte para historial de
accesos o consultas operativas.

## Rol En El Sistema

En un backend financiero, este tipo de bloque sirve para:

- ver accesos relevantes
- responder tickets o dudas de soporte
- complementar auditoria funcional

## Casos De Uso

- investigar si un usuario reporta acceso no reconocido
- revisar contexto de seguridad de una incidencia
- apoyar operaciones internas sin tocar el core de autenticacion

## Relacion Con Otros Modulos

- `identity.sessions` y `identity.devices`
  fuente natural de accesos o contexto de seguridad.
- `support.audit`
  auditoria funcional complementaria.
- `security`
  señales de seguridad o abuso.

## Estado Actual

La subapp esta instalada, pero en esta pasada no detecte una superficie rica ya
materializada. Debe leerse como contexto de soporte preparado.
