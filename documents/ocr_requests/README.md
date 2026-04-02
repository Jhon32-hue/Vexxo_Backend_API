# documents.ocr_requests

## Que hace

`documents.ocr_requests` existe para representar solicitudes de OCR sobre
documentos financieros.

## Estado Del Codigo

Hoy esta en scaffold:

- `models.py` vacio
- `views.py` vacio

## Rol En El Producto

OCR es valioso para:

- convertir recibos o facturas en datos estructurados
- ayudar en registro manual
- acelerar conciliacion y soporte documental

## Relacion Con Otros Modulos

- `documents.files`
  origen del archivo a procesar.
- `documents.metadata`
  destino de lo extraido.
- `finance.transactions`
  potencial vinculacion con ledger.
- `alerts`
  futuras alertas por documentos procesados o pendientes.

## Encaje Con GCP

Este modulo esta claramente alineado con:

- Cloud Storage
- Cloud Run workers
- Document AI o proveedores OCR
- Cloud Tasks para jobs asincronos

## Estado Actual

La frontera conceptual esta clara, pero no hay implementacion productiva visible
hoy.
