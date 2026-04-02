# documents.metadata

## Que hace

`documents.metadata` existe para guardar metadata estructurada de documentos:

- etiquetas
- clasificacion
- entidad relacionada
- estado de procesamiento

## Estado Del Codigo

Hoy esta en scaffold:

- `models.py` vacio
- `views.py` vacio

## Relacion Con Otros Modulos

- `documents.files`
  archivo base.
- `documents.ocr_requests`
  fuente natural de metadata extraida.
- `finance.transactions`
  posible destino de relaciones contables.

## Encaje Con GCP

Es natural que este contexto persista metadata en Cloud SQL mientras los
binarios viven en Cloud Storage y los resultados de OCR llegan por jobs.

## Estado Actual

No hay superficie funcional visible hoy.
