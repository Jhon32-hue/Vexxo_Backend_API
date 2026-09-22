# reports.exports

## Que hace

`reports.exports` existe como contexto para exportaciones de reporting:

- archivos descargables
- paquetes para soporte
- artefactos de analitica o auditoria

## Estado Del Codigo

El modulo esta operativo con jobs durables, cifrado obligatorio, expiracion,
descarga de un solo uso y purga criptografica del artefacto.

## Relacion Con Otros Modulos

- `reports.reports`
  agrega datos de ledger.
- `reports.summaries`
  podria producir snapshots compactos.
- `documents.storage`
  destino natural de archivos de export.
- `support.audit`
  trazabilidad de quien exporto que.

## Encaje Con GCP

Cuando madure, este modulo tiene una relacion muy clara con:

- Cloud Storage para archivos
- Cloud Run workers para generar exports
- Cloud Tasks o Scheduler para jobs asincronos

## Estado Actual

Los exports se crean desde snapshots inmutables, se procesan mediante
`scheduler-local`, se cifran y expiran 24 horas despues de quedar listos. El
token de descarga se entrega una vez y solo se persiste su hash.

`reports.process_exports` genera los artefactos y `reports.purge_exports`
elimina ciphertext, nonce y DEK envuelto una vez vencida la retencion. Un
`legal_hold` impide la purga y el registro restante funciona como tombstone de
auditoria.

API: `POST /api/reports/exports/` y `GET
/api/reports/exports/{uuid}/download/` con `X-Download-Token`. El keyring es
obligatorio: nunca se produce un export sensible sin cifrar.
