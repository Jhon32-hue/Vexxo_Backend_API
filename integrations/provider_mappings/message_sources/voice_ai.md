# Voice AI

## Clasificacion

- categoria primaria: `voice_inferred`
- bounded context principal: `finance.transactions`
- runtime temporal: `integrations_stub.llm`
- servicio futuro esperado: `llm_gateway`
- contrato canonico: `voice_inferred.normalized_payload`

## Regla de frontera

Voz no es CRUD manual mejorado.

El cliente crea una `TransactionInferenceRequest`, el worker de IA transcribe y
extrae filas, y `finance.transactions` aplica el resultado por intake canonico.
El worker no escribe `Transaction` directo ni confirma movimientos.
El `POST` publico solo envia audio y metadatos; no acepta filas inferidas ni
`raw_payload` arbitrario desde cliente.

## Persistencia

- `TransactionInferenceRequest`: estado operativo, audio, idempotencia, errores,
  retries y vinculo al batch.
- `TransactionIntakeBatch`: agrupacion canonica del resultado inferido.
- `TransactionIntakeReceipt`: resultado por fila inferida.
- `TransactionExternalDetails`: transcripcion, parser, confianza y
  `needs_user_confirmation`.

## Idempotencia

- La solicitud publica exige `X-Request-Id` e `Idempotency-Key`.
- Cloud Tasks usa nombre deterministico por `inference_request_id`.
- `AlreadyExists` en Cloud Tasks se trata como exito idempotente, no como falla.
- El batch de resultado usa `idempotency_key` derivado de la solicitud.
- Cada fila debe traer `external_id`; si falta, se deriva de
  `inference_request_id:item-N`.

## Estados operativos

- `queued`: lista para worker.
- `processing`: worker/proveedor activo.
- `transcription_failed`: no hubo texto util.
- `extraction_failed`: no hubo filas canonicas aplicables.
- `applied`: batch aplicado.
- `partial`: batch aplicado con resultado parcial.
- `dead_letter`: retries agotados.
- `canceled`: solicitud anulada.

## Fallbacks

- Si Cloud Tasks no esta listo y el entorno permite fallback local,
  `transaction_inference_dispatch_service.py` deja la solicitud para que un
  worker local durable la tome desde BD.
- En produccion sin Cloud Tasks listo, el dispatcher no ejecuta fallback local.
- Si la transcripcion o extraccion falla, no se crea ledger.
- El worker ignora solicitudes terminales o fuera de `queued`.
- Un sweeper operativo puede recuperar `queued` viejas y `processing` stale.

## Confirmacion de usuario

Cada movimiento inferido debe iniciar con:

- `status=pending`
- `confirmed=false`
- `rail=manual`
- `channel=voice`
- `data_origin=inferred`
- `needs_user_confirmation=true`
- `inference_status=needs_confirmation`

El usuario confirma, edita o rechaza el borrador. El rechazo usa la accion
explicita `rechazar_inferida`.
