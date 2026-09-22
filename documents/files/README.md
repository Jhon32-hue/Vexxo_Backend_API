# documents.files

Representa archivos privados de un usuario. `DocumentFile` persiste nombre
original, MIME, tamano, SHA-256, estado y ruta interna aleatoria.

La subida es idempotente por `owner + sha256`. Un archivo de otro usuario nunca
aparece en list/retrieve y el borrado es logico para conservar trazabilidad.
Los binarios se guardan bajo `MEDIA_ROOT/documents/<owner>/` con nombre UUID.

API: `GET|POST /api/documents/files/`, `GET|DELETE
/api/documents/files/{uuid}/` y `POST .../{uuid}/request-ocr/`.

## Seguridad Del Archivo

Con keyring activo, los archivos nuevos usan AES-256-GCM con DEK por archivo y
KEK versionada; SHA-256 representa siempre el contenido original. Antes de
persistir se ejecuta `basic` (politica minima/EICAR) o ClamAV por INSTREAM.
Los historicos sin cifrar siguen legibles para migracion progresiva.

`POST .../{uuid}/download-grant/` emite un token temporal cuyo hash es lo unico
persistido. `GET /api/documents/downloads/{grant}/` exige `X-Download-Token`, no
permite cache y consume el grant una sola vez.
