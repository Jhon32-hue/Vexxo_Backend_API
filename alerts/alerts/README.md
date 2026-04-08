# alerts.alerts

## Que hace

Gestiona alertas de producto y su enriquecimiento con IA.

No deberia resolver IA pesada dentro del request path principal. La regla es:

- crear alerta rapido
- emitir `alerts.created.v1`
- despachar enriquecimiento IA a worker/cola
- publicar `alerts.ai.enriched.v1` cuando termina

## Rol En El Producto

Este modulo es la capa que convierte eventos financieros y operativos en
mensajes accionables para el usuario.

De cara al cliente:

- ayuda a detectar cambios relevantes
- resume anomalias, riesgo o friccion operativa
- complementa dashboard, cuentas y pagos con contexto util
- prepara explicaciones e insights que luego pueden mostrarse en mobile/web

No reemplaza el ledger ni a `accounts`; interpreta lo que otros contextos ya
registraron.

## Flujo actual

### Creacion

1. `alerts.alerts.services.create_alert()` persiste la alerta.
2. Encola `alerts.created.v1` en outbox.
3. En local puede autopublicarse after-commit; en cloud lo publica un worker.
4. Un listener despacha el enriquecimiento IA mediante
   `alerts.alerts.dispatch_service`.

### Enriquecimiento IA

`dispatch_service` intenta:

- Cloud Tasks hacia `alerts/internal/ai-worker/` si la infraestructura esta lista
- fallback local controlado solo en entornos permitidos

El endpoint interno ejecuta `alerts.alerts.ai_services.enrich_alert_with_ai()`.

### Consumo por mobile/web

1. `accounts`, `transactions` o `payments` emiten eventos
2. `alerts` decide si crear una alerta o enriquecer una existente
3. la alerta queda persistida
4. otras superficies como notificaciones, inbox o dashboard consumen ese
   resultado

## Casos De Uso

- saldo anomalo o movimiento relevante
- cuenta con sync fallido o stale
- drift o recalculo relevante de balance
- friccion de pago o fallo externo
- insight resumido a partir de patrones o IA

## Relacion con otros modulos

- `finance.accounts`: produce eventos de balance/sync que disparan alertas
- `finance.transactions`: puede aportar hechos contables para alertas
- `payments.payment_intents`: aporta eventos operativos de pagos externos
- `identity.users`: consume `alerts.*` para refrescar usage projection
- `notifications`: puede convertir alertas o eventos relacionados en inbox
- `realtime`: puede ayudar a reflejar cambios interactivos de bajo costo
- futuro `llm_gateway`: destino natural de este flujo cuando salga del monolito

## Encaje Con GCP

La forma esperada de operar en GCP es:

- API Gateway / BFF crea o consulta alertas rapido
- Cloud Run worker o Cloud Tasks ejecuta enriquecimiento asincrono
- `llm_gateway` puede vivir como servicio separado en Cloud Run
- Gemini u otro modelo se consume fuera del request principal
- Pub/Sub puede distribuir eventos relevantes a analytics o pipelines

El principio es:

- request corto
- enriquecimiento pesado fuera del request path
- eventos claros para trazabilidad y producto

## Politicas Del Modulo

- una alerta puede existir sin IA; la IA es enriquecimiento, no precondicion
- el listener no debe bloquear el request original del dominio fuente
- si la infraestructura async no esta lista, solo se permite fallback local
  controlado
- el futuro `llm_gateway` debe respetar la misma frontera publica del modulo
- `alerts` no debe volver a publicar eventos criticos directo desde el request
  path; usa outbox como los demas bounded contexts fuertes

## Estado operativo actual

`alerts` ya tiene outbox propio para `alerts.created.v1`.

Eso permite:

- retry
- dead-letter
- worker dedicado
- autopublish local sin romper la topologia cloud

Todavia no implica que todo `alerts.*` tenga ya la misma riqueza operativa de
`accounts`.

## Esqueleto/futuro

Cuando exista un servicio dedicado de IA, este modulo ya tiene la frontera:

- `dispatch_service` se mantiene como orquestador
- el worker interno puede reemplazarse por `llm_gateway`
- la API publica de alertas no necesita cambiar
