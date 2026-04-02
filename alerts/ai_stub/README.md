# alerts.ai_stub

## Que hace

`alerts.ai_stub` representa una frontera temporal para integracion de IA o
simulacion de enriquecimiento de alertas.

## Estado Del Codigo

Hoy esta en scaffold:

- `models.py` vacio
- `views.py` vacio
- sin endpoints, servicios ni contratos visibles

## Relacion Con Otros Modulos

La IA operativa de alertas que hoy si se detecta vive en:

- `alerts.alerts.ai_services`
- `alerts.alerts.dispatch_service`
- `alerts.alerts.event_handlers`

`ai_stub` queda como una pieza de apoyo o placeholder, no como la frontera
canonica actual.

## Rol En El Producto

El concepto sigue siendo util cuando se necesita:

- probar enriquecimiento sin depender del gateway LLM real
- desacoplar feature flags o proveedores de IA
- mantener una frontera temporal mientras la integracion cloud madura

## Encaje Con GCP

La frontera final de IA de Vexxo esta pensada para trabajar con:

- `llm_gateway`
- Gemini u otro proveedor
- Cloud Run workers
- Cloud Tasks para jobs asincronos

Este app hoy no implementa esa capa.

## Estado Actual

Contexto reservado, no feature productiva cerrada.
