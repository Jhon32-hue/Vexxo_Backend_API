# api.v1

## Que hace

`api.v1` contiene la superficie HTTP versionada principal del backend.

## Rol En El Sistema

Este submodulo no modela negocio por si mismo. Su responsabilidad es ensamblar
los routers y exponer una API estable para mobile y web.

## Flujo Principal

1. `backend.urls` monta `api/`
2. `api.v1.routers` registra las rutas versionadas
3. cada bounded context expone su superficie por viewsets o vistas
4. mobile/web consume esa capa unificada como BFF

## Relacion Con Otros Modulos

- `backend.urls`
  monta `api/` sobre `api.v1.routers`.
- los bounded contexts del proyecto
  registran aqui sus viewsets, APIs o endpoints cuando corresponde.
- `api.throttling`
  puede complementar esta capa con proteccion de consumo.

## Encaje Con GCP

En despliegue cloud-first, `api.v1` es la puerta versionada que vive detras de:

- API Gateway
- Cloud Armor
- Cloud Run BFF

## Estado Actual

Su `AppConfig` existe y forma parte del ensamblaje del proyecto. La logica
detallada de endpoints y routers se documenta mejor en `api/README.md` y en los
modulos de negocio expuestos por esa API.
