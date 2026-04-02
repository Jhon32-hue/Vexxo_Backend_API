# social.contacts

## Que hace

`social.contacts` existe como contexto social reservado para relaciones entre
usuarios o participantes, distinto del modulo operativo `contacts/`.

## Importante

Hoy el modulo real de contactos financieros reutilizables del producto es
`contacts`, no este app.

## Estado Del Codigo

Este submodulo social esta en scaffold:

- `models.py` vacio
- `views.py` vacio

## Relacion Con Otros Modulos

- `contacts`
  resuelve el caso operativo actual de contactos financieros.
- `social.teams`
  puede aportar relaciones de grupo.
- `payments`
  podria usar contactos como beneficiarios futuros.

## Estado Actual

No debe documentarse como capacidad activa. El contexto existente y usable hoy
para contactos es `contacts/`.
