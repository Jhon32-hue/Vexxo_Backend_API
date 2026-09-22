# Security foundation

`security` es la capa transversal operativa para controles que no pertenecen a
un bounded context financiero. No reemplaza permisos, ownership ni validaciones
de dominio.

## Implementado

- clasificacion `public | internal | confidential | restricted`
- masking de correo, telefono, documentos, cuentas y tokens
- redaccion de logs JSON antes de escribir en consola
- validadores de metadata, URL, nombre de archivo y ordering allowlisted
- throttle durable PostgreSQL para login, recovery y webhooks
- `SecurityAuditEvent` append-only para eventos de seguridad minimizados
- AES-256-GCM con envelope encryption para credenciales de integraciones
- keyring versionado: una llave activa escribe y las anteriores solo leen
- rewrap durable por lotes con `security.key_rotation`
- estado integrado al dashboard staff-only
- escaneo de secretos, entropia, llaves privadas, `.env` e historial Git en CI
- catalogo de politica para los 110 `JSONField` actuales
- auditoria estricta de filtros y ordering de las 117 vistas API actuales
- purga durable y por lotes de auditoria, throttling y challenges vencidos

## Clasificacion

| Nivel | Ejemplos | Regla |
|---|---|---|
| `public` | catalogos publicados | Puede salir por API publica. |
| `internal` | IDs tecnicos, metricas agregadas | Solo operacion autenticada. |
| `confidential` | correo, telefono, movimientos | Owner/support autorizado y masking. |
| `restricted` | JWT, OAuth tokens, llaves, CVV/PIN | Nunca logs/metadata; cifrado o no persistencia. |

`safe_metadata` rechaza claves sensibles, objetos de mas de 16 KiB, profundidad
mayor a cinco y colecciones de mas de cien elementos. El payload externo crudo
no se convierte en metadata segura por renombrarlo.

## Operacion local

Los secretos quedan vacios en `.env.local.example`. Configuralos solo en
`.env.local`, que esta excluido de Git:

```powershell
[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(64))
[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

La primera salida puede usarse para JWT/recovery/throttle. La segunda es una
KEK de cifrado. Variables:

```dotenv
VEXXO_LOCAL_JWT_SIGNING_KEY=
VEXXO_LOCAL_IDENTITY_RECOVERY_HASH_KEY=
VEXXO_LOCAL_SECURITY_THROTTLE_HASH_KEY=
VEXXO_LOCAL_SECURITY_ENCRYPTION_ACTIVE_KEY_VERSION=v1
VEXXO_LOCAL_SECURITY_ENCRYPTION_KEYS_JSON={"v1":"BASE64_DE_32_BYTES"}
```

Comandos:

```powershell
.\scripts\run_stack.cmd local security-status
.\scripts\run_stack.cmd local key-rotation-status
.\scripts\run_stack.cmd local rotate-keys full --limit 25
docker compose -f docker-compose.local.yml exec -T api python manage.py security_purge_retention
docker compose -f docker-compose.local.yml exec -T api python manage.py api_filter_audit --strict
```

## Rotacion de cifrado

1. Agregar `v2` al JSON sin retirar `v1`.
2. Cambiar la version activa a `v2` y reiniciar los procesos.
3. Ejecutar `run_worker security.key_rotation` hasta que no haya pendientes.
4. Verificar credenciales y documentos con `key_rotation_status`.
5. Ejecutar `key_retirement_check v1` y probar el backup.
6. Retirar `v1` solo cuando su conteo llegue a cero.

Cada secreto usa un DEK aleatorio. La rotacion reenvuelve ese DEK con la nueva
KEK; el ciphertext del proveedor no se descifra ni se vuelve a escribir.

JWT usa un keyring multi-version. Los tokens nuevos incluyen `kid`; durante una
rotacion, las llaves anteriores retenidas siguen validando tokens no expirados.
La secuencia es agregar la nueva version, activarla, esperar el TTL maximo de
refresh y retirar la anterior. `security_status` muestra versiones sin secretos.

## Fronteras

- Passwords se hashean con Django; nunca se cifran reversiblemente.
- Biometria se procesa en el dispositivo y nunca llega al backend.
- `LocMemCache` puede seguir sirviendo cache no critico; los limites sensibles
  usan `SecurityThrottleBucket` en PostgreSQL.
- Cloud KMS/Secret Manager son adapters futuros. El modelo y los envelopes no
  dependen de ellos.

TOTP guarda la semilla como `IntegrationCredential` cifrada, los recovery codes
solo como hash y rechaza replay. La prueba Ed25519 de dispositivo demuestra
posesion de clave, pero no se reporta como Play Integrity/App Attest.

## Activacion y auditoria

- `security_activation_check` comprueba keyring, antivirus, attestation,
  open banking y pagos sin imprimir credenciales.
- `json_field_audit --details` inventaria todos los `JSONField` y marca
  candidatos por nombre que requieren revision adicional.
- `json_field_audit --scan-data --strict` comprueba la politica resuelta y una
  muestra configurable de los datos persistidos.
- `api_filter_audit --strict` falla ante ordering dinamico o backends sin
  allowlist explicita.
- El inventario es solo lectura: cada campo se migra con esquema y retencion
  propios; no se trunca metadata financiera historica automaticamente.

La ausencia de `validate_safe_metadata` en un outbox o snapshot interno no es
por si sola una vulnerabilidad: esa validacion corresponde al borde de ingreso.
La politica, clasificacion y escaneo siguen aplicando al campo persistido.
Cada campo declara ademas `validation_boundary=model|service|internal`, perfil
de validacion y tamano maximo. El modo estricto falla si una frontera `model`
no tiene el validador esperado; los candidatos por nombre permanecen como
telemetria informativa y no sustituyen la politica revisada.

Runbooks canonicos:

- [Politica de datos](../docs/DATA_SECURITY_POLICY.md)
- [Gestion y recuperacion de llaves](../docs/KEY_MANAGEMENT_RUNBOOK.md)
- [Garantias de identidad y dispositivo](../docs/IDENTITY_SECURITY_ASSURANCE.md)
