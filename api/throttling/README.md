# api.throttling

## Que hace

`api.throttling` existe como submodulo tecnico para rate limiting o control de
consumo de la API.

## Estado Del Codigo

Hoy la presencia visible en esta pasada es su `AppConfig`, sin una superficie
documentable rica equivalente a otros contextos.

## Rol En El Sistema

Su responsabilidad natural es proteger el BFF contra:

- abuso
- bursts descontrolados
- clientes mal configurados
- presion innecesaria sobre el request path

## Casos De Uso

- limitar abuso por cliente o token
- proteger endpoints sensibles
- suavizar picos de consumo
- complementar politicas edge con controles a nivel app

## Relacion Con Otros Modulos

- `api.v1`
  superficie protegida.
- `security`
  frontera de politicas de proteccion y limites.
- `observability`
  metrica y seguimiento de saturacion o limites alcanzados.

## Encaje Con GCP

Este submodulo se complementa con:

- API Gateway
- Cloud Armor
- politicas edge de seguridad

## Estado Actual

Subapp tecnica preparada; la politica efectiva de throttling no esta
centralmente visible aqui en esta pasada.
