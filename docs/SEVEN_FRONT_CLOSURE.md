# Cierre de los siete frentes

## Criterio

Un frente se considera cerrado para desarrollo local cuando tiene contrato,
implementacion, controles fail-closed, pruebas y operacion documentada. Una
certificacion que depende de credenciales, sandbox, tienda o hardware real no
se falsifica: queda como compuerta externa visible y el proveedor permanece no
disponible hasta superarla.

## Estado

| Frente | Cierre local y contractual | Compuerta externa |
| --- | --- | --- |
| Plataforma de seguridad | 110 `JSONField` registrados; clasificacion, esquema, retencion, tamano, redaccion, borrado y frontera `model/service/internal`; filtros auditados; throttling y retencion PostgreSQL; secret scan CI. | Revisiones regulatorias periodicas. |
| Cifrado y llaves | AES-256-GCM, DEK por secreto, keyring versionado, rewrap durable, retiro seguro, backup DPAPI local y drill real `v1 -> v2`. Documentos cuentan para retiro. | KMS/Secret Manager cuando vuelva la nube. |
| Identidad | Recovery anti-enumeracion, MFA, JWT multi-key, familias persistentes, revocacion por password/dispositivo/suspension/riesgo, Ed25519 y lifecycle de attestation. | Play Integrity desde Play y App Attest desde hardware Apple. |
| Integraciones | Credenciales separadas, cuarentena, lifecycle de consentimiento, cursores, retries, webhooks, normalizacion, reconcile y timeline de soporte. | Belvo/Salt Edge requieren credenciales y vector oficial con checksum antes de `available=true`. |
| Finanzas, documentos y reportes | Reconciliacion sin autoajuste, procedencia/versiones, PSP fake, casos de reverso/disputa, cierres versionados, cifrado documental, ClamAV, OCR lineage y exports de un uso. | PSP/bancos reales y politicas legales finales de retencion. |
| Flutter | Tokens separados, SQLCipher por usuario, retencion offline, biometria local, MFA, Ed25519, bridges nativos de attestation y pin activo+respaldo. | Pins reales, Play track y prueba iOS/TestFlight. |
| Open Banking | Contrato canonico, golden data sintetica, instituciones, cuarentena, dedupe, transiciones, reconciliacion, soporte auditado e integracion con ledger. | Golden vectors oficiales y sandbox certificado de un proveedor elegido. |

## Comandos de evidencia

```powershell
.\scripts\run_stack.ps1 local verify full
.\scripts\run_stack.ps1 local status full
docker compose --env-file .env.local -f docker-compose.local.yml exec -T api python manage.py security_activation_check
docker compose --env-file .env.local -f docker-compose.local.yml exec -T api python manage.py json_field_audit --scan-data --strict
docker compose --env-file .env.local -f docker-compose.local.yml exec -T api python manage.py api_filter_audit --strict
docker compose --env-file .env.local -f docker-compose.local.yml exec -T api python manage.py open_banking_certification_status --strict
```

El modo estricto exige que el runtime local este listo; no obliga a habilitar
proveedores externos. El detalle muestra por separado credenciales,
certificacion oficial y disponibilidad.

## Baseline validado

Validacion local ejecutada el 19 de septiembre de 2026:

- 228/228 pruebas backend descubiertas por `run_stack local test full`.
- 139/139 pruebas de finanzas, pagos, documentos, reportes y Open Banking.
- 43/43 pruebas de seguridad, identidad, dispositivos, sesiones, consentimientos
  y permisos.
- 21/21 pruebas de soporte, dashboard, scheduler, health, notificaciones y
  alertas.
- 19/19 pruebas Flutter y `flutter analyze` sin hallazgos.
- 110/110 `JSONField` clasificados, sin politicas invalidas ni filas rechazadas.
- 117 vistas auditadas sin filtros u ordering dinamicos inseguros.
- `django check`, `makemigrations --check` y escaneo de secretos correctos.
- Docker local saludable con API, PostgreSQL, scheduler y ClamAV.
- APK Android `devDebug` compilada mediante truststore local aislado.

La suite por modulos es la referencia porque el descubrimiento Django desde la
raiz no recorre de forma confiable todos los archivos de prueba de esta
estructura historica.

## Regla de crecimiento

- Una funcionalidad nueva no se registra por entorno.
- Un nuevo job durable se declara una vez en el catalogo comun.
- Un nuevo `JSONField` debe declarar politica y frontera de validacion.
- Un nuevo proveedor implementa el adapter comun y su certificacion; nunca
  escribe directamente el ledger.
- Flutter sugiere y captura contexto. Backend conserva permisos y verdad
  contable.
