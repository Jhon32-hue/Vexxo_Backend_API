# social.teams

## Que hace

`social.teams` modela equipos y membresias sociales dentro del producto.

Su responsabilidad actual es:

- CRUD de equipos
- CRUD de miembros del equipo
- enforcement basico de ownership sobre la gestion del team

## Rol En El Producto

Este contexto es la base social general de Vexxo fuera del sharing especifico
de cuentas.

Puede servir para:

- grupos
- colaboracion social
- experiencias compartidas futuras

## Flujo Principal

1. el usuario crea un equipo
2. automaticamente se vuelve owner y miembro activo
3. el owner invita o gestiona miembros
4. solo miembros activos ven sus equipos
5. solo el owner puede borrar el equipo o administrar miembros

## Relacion Con Otros Modulos

- `finance.accounts`
  cubre sharing financiero especifico por cuenta
- `social.teams`
  cubre agrupacion social mas general

En el futuro ambos contextos pueden colaborar, pero no deben mezclarse.

## Encaje Con GCP

Hoy es una superficie CRUD/autorizacion sobre Cloud SQL + Cloud Run.

La evolucion futura podria incluir:

- invitaciones mas ricas
- eventos sociales
- integracion con planning o gastos compartidos

## Estado Actual

El enforcement visible en código hoy es:

- `TeamViewSet`
  lista solo equipos donde el usuario es miembro activo
- `MembershipViewSet`
  permite gestionar miembros solo si el usuario es owner del equipo

Es un contexto funcional pero aun liviano.
