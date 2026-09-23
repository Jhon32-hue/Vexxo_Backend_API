# Vexxo Postman Collection

Fuente importable: [Vexxo_local.postman_collection.json](Vexxo_local.postman_collection.json)

La coleccion es un catalogo operativo local del backend. El archivo se genera desde
`scripts/generate_postman_collection.py` para mantener estructura, variables y guia sincronizadas.

## Regeneracion

```powershell
.\scripts\run_manage_vexxo_app.cmd shell --command "print('runtime ok')"
py -3 .\scripts\generate_postman_collection.py
```

La generacion no necesita Django ni credenciales. La primera linea solo verifica opcionalmente el runtime.

## Seguridad

- No guardar tokens, API keys, passwords reales ni secretos de proveedores en el JSON.
- `internal_token` empieza vacio y debe configurarse localmente o mediante Postman Vault.
- `support_access_token` es independiente del token del usuario y debe pertenecer a staff local.
- Las consultas de soporte exigen `support_reason`; `support_case` identifica el ticket asociado.
- Las carpetas internas no son superficie publica para Flutter.
- `90 - Planned Contracts` documenta fronteras futuras y no contiene endpoints inventados.

## Flujo minimo

1. `00 / Health` y `Readiness`.
2. `01 / Register` o `Login`.
3. `02 / Mobile Bootstrap` hasta que el test confirme el bootstrap asincrono y guarde `category_id`.
4. `04 / List Accounts` para reutilizar una cuenta o `Create Cash Account` para crearla.
5. `05 / Create Manual Expense` para guardar `transaction_id`.
6. `06 / Create Category Budget`.
7. Consultar alertas, notificaciones, realtime y auditoria.
8. Para soporte, obtener aparte un token staff, asignarlo a `support_access_token` y ejecutar `16`.

## Secciones

| Seccion | Requests | Proposito |
|---|---:|---|
| `00 - Start Here and Runtime` | 2 | Punto de entrada. Verifica runtime antes de ejecutar flujos. No contiene secretos ni valores cloud. |
| `01 - Authentication and User Access` | 15 | Autenticacion, recuperacion, step-up y proveedores sociales. |
| `02 - Mobile BFF` | 3 | Contratos de arranque y sincronizacion incremental de Flutter. |
| `03 - Identity, Security and User Types` | 32 | Perfil, dispositivos, sesiones, consentimientos, permisos y administracion. |
| `04 - Accounts, Cash and Sharing` | 28 | Cuentas manuales/conectadas, efectivo, sharing, sync e inteligencia. |
| `05 - Transactions and Ledger` | 21 | Ledger canonico, consultas estandar, voz, clasificacion y participantes. |
| `06 - Budgets` | 11 | Presupuesto personal y compartido con metricas del ledger. |
| `07 - Scheduled Payments` | 12 | Plantillas, corridas, vencimientos y materializacion de pagos. |
| `08 - Payments and Providers` | 12 | Pricing, intents, payouts, callbacks, settlement y contratos por proveedor. |
| `09 - Alerts and Rules` | 7 | Alertas de producto, acciones y reglas configurables. |
| `10 - Notifications and Realtime` | 11 | Inbox durable, preferencias y senales de UX. |
| `11 - Documents and OCR` | 8 | Archivos privados, OCR durable y vinculacion al ledger. |
| `12 - Contacts and Teams` | 8 | Contactos, equipos y base social para gastos compartidos. |
| `13 - Shared Expenses` | 8 | Division, invitacion, acceptance, disputa y settlement sin duplicar el ledger. |
| `14 - Finance Catalogs and Planning` | 19 | Categorias, comercios, FX, deudas y metas. |
| `15 - Reports and Standard Queries` | 8 | Consultas agregadas para producto, soporte y analitica. |
| `16 - Open Banking` | 9 | Consentimiento, catalogo, cuentas, sync, reconciliacion y revocacion local-first. |
| `17 - Internal Integrations and Services` | 8 | Solo adapters/workers. Requiere internal_token y no es API mobile publica. |
| `18 - Eventing and Operations` | 9 | Outboxes, contratos, health, retries y locks. |
| `19 - Support and Audit` | 7 | Consultas read-only para soporte y auditoria. |
| `90 - Planned Contracts - Not Executable` | 0 | Roadmap contractual. Estas carpetas no inventan endpoints: documentan fronteras futuras hasta que exista implementacion y pruebas. |

## Variables

Las variables de IDs se llenan desde tests de Postman cuando una respuesta exitosa contiene el recurso.
`current_date`, `current_month` y `request_id` se recalculan antes de cada request.

## Mantenimiento

Cuando se agregue un endpoint:

1. Agregarlo al bounded context correspondiente en el generador.
2. Incluir descripcion, rol esperado, body minimo y codigos validos.
3. Capturar su ID si alimenta requests posteriores.
4. Regenerar JSON y guia.
5. Validar el JSON y ejecutar al menos el flujo minimo local.
6. Reimportar la coleccion en Postman reemplazando `Vexxo_API`.
