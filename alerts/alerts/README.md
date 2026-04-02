# alerts.alerts

## Que hace

Gestiona alertas de producto y su enriquecimiento con IA.

No deberia resolver IA pesada dentro del request path principal. La regla es:

- crear alerta rapido
- emitir `alerts.created.v1`
- despachar enriquecimiento IA a worker/cola
- publicar `alerts.ai.enriched.v1` cuando termina

## Flujo actual

### Creacion

1. `alerts.alerts.services.create_alert()` persiste la alerta.
2. Publica `alerts.created.v1`.
3. Un listener despacha el enriquecimiento IA mediante
   `alerts.alerts.dispatch_service`.

### Enriquecimiento IA

`dispatch_service` intenta:

- Cloud Tasks hacia `alerts/internal/ai-worker/` si la infraestructura esta lista
- fallback local controlado solo en entornos permitidos

El endpoint interno ejecuta `alerts.alerts.ai_services.enrich_alert_with_ai()`.

## Relacion con otros modulos

- `finance.accounts`: produce eventos de balance/sync que disparan alertas
- `identity.users`: consume `alerts.*` para refrescar usage projection
- futuro `llm_gateway`: destino natural de este flujo cuando salga del monolito

## Esqueleto/futuro

Cuando exista un servicio dedicado de IA, este modulo ya tiene la frontera:

- `dispatch_service` se mantiene como orquestador
- el worker interno puede reemplazarse por `llm_gateway`
- la API publica de alertas no necesita cambiar
