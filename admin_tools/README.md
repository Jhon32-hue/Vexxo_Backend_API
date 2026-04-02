# admin_tools

## Que hace

`admin_tools` agrupa herramientas internas para operacion, soporte y revision
manual del sistema.

## Submodulos Presentes

- `dashboards`
- `user_lookup`
- `manual_adjustments`
- `alert_review`
- `audit_trails`

## Rol En El Sistema

Estas piezas no son parte de la experiencia B2C principal. Su lugar es apoyar:

- soporte
- operaciones
- revisiones manuales
- inspeccion interna del estado del sistema

## Principio Operativo

Estas herramientas deben permanecer:

- separadas de la API publica
- protegidas por permisos internos
- auditables
- alineadas con soporte y operaciones, no con features de usuario final

## Relacion Con Otros Modulos

- `support.audit`
  trazabilidad funcional.
- `identity`
  lookup o soporte sobre usuario y acceso.
- `alerts`
  revision o triage de alertas.
- `finance` y `payments`
  ajustes o inspecciones operativas cuando aplique.

## Encaje Con GCP

Estas herramientas pueden vivir sobre el mismo backend en Cloud Run, pero deben
mantener separacion fuerte de permisos y autenticacion respecto a la API B2C.

## Estado Actual

El bloque existe e incluso esta instalado en Django, pero en esta pasada no
detecte una superficie rica en cada subapp. Se documentan como herramientas
internas preparadas.
