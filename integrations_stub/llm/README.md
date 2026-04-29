# integrations_stub.llm

## Que hace

`integrations_stub.llm` es el runtime temporal para tareas de IA que despues
deberian vivir en un `llm_gateway` separado.

Hoy cubre inferencia de transacciones por voz:

1. recibe `inference_request_id`
2. carga `TransactionInferenceRequest`
3. transcribe/extrae o simula el resultado desde `raw_payload`
4. devuelve filas `voice_inferred.normalized_payload`
5. delega la aplicacion a `finance.transactions.transaction_inference_service`

`raw_payload` en este stub es solo un mecanismo interno de simulacion. El
endpoint publico de mobile no puede enviar filas normalizadas al crear la
solicitud.

## Regla de frontera

El stub no es fuente de verdad y no escribe ledger.

La fuente de verdad del estado de mobile es `TransactionInferenceRequest` en
`finance.transactions`. La materializacion final pasa por
`TransactionIntakeBatch`, `TransactionIntakeReceipt` y `TransactionSourceLink`.

## Rutas

| Ruta | Metodo | Auth | Uso |
|---|---|---|---|
| `/api/internal/integrations/llm/transactions/inference/worker/` | `POST` | `X-Vexxo-Internal-Token` | procesa solicitud de voz |
| `/internal/integrations/llm/transactions/inference/worker/` | `POST` | `X-Vexxo-Internal-Token` | prefijo legacy compatible |

Payload minimo:

```json
{
  "inference_request_id": "00000000-0000-0000-0000-000000000000",
  "request_id": "mobile-request-001",
  "source": "cloud_tasks"
}
```

## Fallback local

Si Cloud Tasks no esta configurado y
`TRANSACTION_INFERENCE_LOCAL_FALLBACK_ENABLED=true`, el dispatcher de
`finance.transactions` encola este stub en un thread de background del mismo
proceso.

En produccion el fallback local se deshabilita automaticamente salvo que el
entorno lo permita explicitamente.

Si Cloud Tasks devuelve `AlreadyExists`, el dispatcher trata la solicitud como
ya encolada y no ejecuta fallback local.

## Fallos

- `transcription_failed`: no se pudo obtener texto util.
- `extraction_failed`: no se pudo estructurar ninguna fila canonica.
- `dead_letter`: se agotaron retries configurados.
- `skipped`: la solicitud ya no estaba en estado procesable y se ignoro para
  evitar reproceso tardio.

En cualquiera de esos estados no se crea ledger. El frontend puede mostrar el
estado y ofrecer retry desde el endpoint publico de `inference-requests`.
