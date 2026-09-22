# Politica de datos estructurados

La politica central aplica a cada `JSONField` descubierto por Django y produce
clasificacion, identificador de esquema, retencion, redaccion, capacidad de
eliminacion, tamano maximo y frontera de validacion. Los overrides protegen
envelopes, credenciales, auditoria y payloads de proveedores; los demas campos
reciben una politica conservadora revisada.

El perfil post-registro `users.UserOnboardingProfile` se clasifica como
`confidential`. Sus listas JSONB (`preferred_currencies`, `income_sources` y
`use_cases`) tienen catalogos cerrados, validacion de modelo, retencion de 365
dias y capacidad de eliminacion. Edad, empleo e ingresos no se publican en
outboxes, logs ni notificaciones.

## Reglas

- `public`: contenido publicable, sin secretos.
- `internal`: estado tecnico y resultados operativos, acceso de soporte limitado.
- `confidential`: finanzas y PII, ownership, masking y borrado sujeto a reglas.
- `restricted`: tokens, evidencia, payload crudo y envelopes; nunca logs o APIs
  generales.
- Metadata segura usa `validate_safe_metadata`; payloads de proveedor usan
  `validate_external_payload` y sanitizacion antes de persistir o registrar.
- Un nombre como `metadata` o `payload` es solo un candidato de auditoria. Los
  outboxes y snapshots generados internamente no deben tratarse como entrada
  directa del cliente.
- `model` exige el validador en el campo, `service` exige sanitizacion en el
  caso de uso canonico e `internal` prohibe tratar el campo como entrada externa.

## Auditoria

```powershell
docker compose -f docker-compose.local.yml exec -T api python manage.py json_field_audit --details --strict
docker compose -f docker-compose.local.yml exec -T api python manage.py json_field_audit --scan-data --limit-per-field 100 --strict
docker compose -f docker-compose.local.yml exec -T api python manage.py api_filter_audit --details --strict
```

`--strict` falla ante un campo sin politica, datos que excedan su perfil o una
superficie de filtros/ordering dinamica no allowlisted. El escaneo es de solo
lectura y no borra metadata historica.

## Retencion

`security.purge_retention` elimina por lotes auditoria vencida segun severidad,
buckets de throttling inactivos, challenges consumidos/vencidos y grants de
descarga antiguos. El scheduler ejecuta el job diario con advisory lock.

```powershell
docker compose -f docker-compose.local.yml exec -T api python manage.py security_purge_retention --limit-per-model 500
```

Los eventos criticos conservan siete anos por defecto; warning dos anos e info
un ano. Cualquier cambio regulatorio debe modificar configuracion y esta
politica antes de purgar datos.
