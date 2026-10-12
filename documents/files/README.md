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

<!-- backend-source-audit:start -->
## Evidencia del codigo y mapa de dependencias

Inventario estatico reproducible del checkout. Describe declaraciones e imports;
no prueba despliegue, permisos efectivos ni que todos los caminos se ejecuten.
Las rutas son locales a su URLConf: el prefijo publico se consulta en
[`api/v1/routers.py`](../../api/v1/routers.py).

- Archivos Python de implementacion: **13** (excluye tests y migraciones).
- Huella SHA-256 del codigo inventariado: `1bb1fdb406ab2690b0c401a75a4e7cd1182eadceba9a4928e5425e2e0c4173e5`.
- Familias detectadas: management, models, serializers, services, views.

### Declaraciones de modelos detectadas

- `DocumentDownloadGrant` en [documents/files/models.py](models.py).
- `DocumentFile` en [documents/files/models.py](models.py).

### Rutas declaradas

| Patron local | Fuente |
| --- | --- |
| `` | [documents/files/urls.py](urls.py) |
| `downloads/ [DRF router]` | [documents/files/urls.py](urls.py) |
| `files/ [DRF router]` | [documents/files/urls.py](urls.py) |

### Diagrama de dependencia estatica

Las flechas representan imports entre paquetes, no eventos ni orden de ejecucion.

```mermaid
flowchart LR
    M["documents.files"]
    M --> D0["security"]
```

Flujos transversales: [flujo actualizado](../../docs/BACKEND_CURRENT_FLOW.md).

Regeneracion: `py -3 scripts/audit_backend_docs.py --write`.
Comprobacion de deriva: `py -3 scripts/audit_backend_docs.py --check`.
<!-- backend-source-audit:end -->
