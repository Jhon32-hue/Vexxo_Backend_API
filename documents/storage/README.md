# documents.storage

## Que hace

`documents.storage` existe para abstraer el almacenamiento fisico de documentos.

## Estado Del Codigo

Hoy esta en scaffold:

- `models.py` vacio
- `views.py` vacio

## Relacion Con Otros Modulos

- `documents.files`
  identidad del archivo.
- `reports.exports`
  artefactos descargables.
- `payments`
  posibles comprobantes o soportes operativos.

## Encaje Con GCP

Este es uno de los contextos con encaje mas directo en la nube:

- Cloud Storage como backend natural
- Cloud KMS si aparece cifrado adicional
- Signed URLs o servicios internos para acceso controlado

## Estado Actual

No hay implementacion funcional visible hoy. Debe leerse como una frontera
planeada para almacenamiento documental.
