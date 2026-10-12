# integrations.credentials

Almacen generico de secretos de proveedores. `IntegrationCredential` guarda
solo un envelope autenticado, version de llave, expiracion, estado y metadata
segura. No existe serializer publico y Django Admin oculta el ciphertext.

Los adapters usan `store_credential`, `reveal_credential`,
`rotate_credential_key` y `revoke_credential`. Open Banking revoca las
credenciales cuyo `external_reference` corresponde a la conexion cuando el
usuario retira el consentimiento.

Los tokens no deben aparecer en `safe_metadata`, eventos, logs, responses ni
Flutter. Consulta [`security/README.md`](../../security/README.md) para configurar
y rotar llaves.

<!-- backend-source-audit:start -->
## Evidencia del codigo y mapa de dependencias

Inventario estatico reproducible del checkout. Describe declaraciones e imports;
no prueba despliegue, permisos efectivos ni que todos los caminos se ejecuten.
Las rutas son locales a su URLConf: el prefijo publico se consulta en
[`api/v1/routers.py`](../../api/v1/routers.py).

- Archivos Python de implementacion: **5** (excluye tests y migraciones).
- Huella SHA-256 del codigo inventariado: `635e4ef0f4345345ebcaa49c49fff02f5c2c56788528401471fd8daf37d70afe`.
- Familias detectadas: models, services.

### Declaraciones de modelos detectadas

- `IntegrationCredential` en [integrations/credentials/models.py](models.py).

No se detectan declaraciones `path`/`re_path` propias en este alcance.
Esto no implica que el modulo carezca de consumidores internos.

### Diagrama de dependencia estatica

Las flechas representan imports entre paquetes, no eventos ni orden de ejecucion.

```mermaid
flowchart LR
    M["integrations.credentials"]
    M --> D0["security"]
```

Flujos transversales: [flujo actualizado](../../docs/BACKEND_CURRENT_FLOW.md).

Regeneracion: `py -3 scripts/audit_backend_docs.py --write`.
Comprobacion de deriva: `py -3 scripts/audit_backend_docs.py --check`.
<!-- backend-source-audit:end -->
