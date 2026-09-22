# documents.ocr_requests

`OcrRequest` es la cola PostgreSQL durable para OCR local. Conserva estado,
engine, intentos, lock, error, texto y datos estructurados. La unicidad
`owner + idempotency_key` evita trabajos duplicados.

El worker usa `select_for_update(skip_locked=True)` y recupera locks
`processing` con mas de 15 minutos. El resultado puede ser
`succeeded`, `review_required` o `failed`; una imagen sin motor/extraccion local
queda para revision humana en vez de producir datos falsos.

El outbox `DocumentDomainEventOutbox` publica `documents.ocr.completed.v1` o
`documents.ocr.review_required.v1` mediante el publisher central.
