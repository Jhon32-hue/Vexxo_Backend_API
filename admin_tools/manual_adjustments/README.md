# admin_tools.manual_adjustments

## Que hace

`admin_tools.manual_adjustments` existe para ajustes manuales internos cuando el
negocio o soporte lo exigen.

## Importante

Por definicion, este tipo de capacidad debe ser excepcional, auditable y muy
protegida.

## Casos De Uso Naturales

- correcciones controladas
- reparacion de datos despues de un incidente
- apoyo manual temporal mientras madura una automatizacion

## Relacion Con Otros Modulos

- `support.audit`
  trazabilidad obligatoria.
- `finance.accounts` y `finance.transactions`
  posibles dominios sensibles a ajustes.
- `payments`
  podria requerir correcciones operativas en casos extremos.

## Estado Actual

La subapp esta instalada, pero no detecte superficie funcional visible en esta
pasada. Debe verse como una frontera interna preparada.
