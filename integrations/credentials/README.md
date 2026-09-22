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
