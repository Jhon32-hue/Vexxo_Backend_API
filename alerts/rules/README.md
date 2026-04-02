# alerts.rules

## Que hace

`alerts.rules` administra reglas configurables del usuario para disparar o
controlar alertas.

Su responsabilidad actual es:

- CRUD de reglas (`Rule`)
- aplicar gating por plan para cantidad de reglas activas
- mantener actualizado el usage projection de reglas

## Rol En El Producto

Este modulo acerca a Vexxo a la automatizacion.

De cara al usuario, permite:

- definir comportamiento repetible
- pasar de alertas puramente reactivas a reglas configuradas
- crear una experiencia mas `pro` sin romper el loop manual base

## Flujo Principal

1. el usuario crea una regla
2. si la regla queda activa, se valida limite por plan
3. la regla se persiste
4. `identity.users.product_usage_projection_service` actualiza `rules_count`
5. al activar, desactivar o eliminar, el uso se ajusta incrementalmente

## Relacion Con Otros Modulos

- `identity.users`
  valida el limite de reglas por plan y guarda uso proyectado
- `alerts.alerts`
  consume o puede reaccionar a la existencia de reglas
- futuros motores de automatizacion pueden ejecutar la logica definida aqui

## Encaje Con GCP

Hoy es una capa CRUD sobre Cloud SQL y Cloud Run.

La evolucion natural es:

- workers o evaluadores async
- triggers por eventos de dominio
- ejecucion desacoplada por Cloud Tasks o Pub/Sub

sin cambiar el rol de este modulo como repositorio de reglas.

## Estado Actual

Hoy `ReglaViewSet`:

- lista solo reglas del owner
- valida limite de plan al crear o activar
- ajusta `rules_count` incrementalmente

Lo que todavia no se documenta como cerrado aqui es un motor rico de ejecucion
de reglas; hoy la superficie fuerte es administracion y policy de uso.
