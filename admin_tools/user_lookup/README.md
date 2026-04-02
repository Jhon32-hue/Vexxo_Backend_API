# admin_tools.user_lookup

## Que hace

`admin_tools.user_lookup` existe para busqueda o inspeccion interna de usuarios.

## Rol En El Sistema

Es una necesidad clasica de soporte:

- localizar un usuario
- revisar contexto basico
- ayudar a investigar problemas

## Principio De Uso

Debe operar siempre con cuidado de privacidad y trazabilidad. Buscar un usuario
internamente es una accion de soporte, no una capacidad neutra.

## Relacion Con Otros Modulos

- `identity.users`
  fuente de verdad del usuario.
- `support.audit`
  auditoria de consultas o acciones internas.

## Estado Actual

Subapp instalada, pero sin una capa publica o servicios ricos detectados en
esta pasada.
