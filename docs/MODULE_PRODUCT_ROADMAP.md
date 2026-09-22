# Evaluacion modular y roadmap de producto

## Proposito

Este documento convierte la estructura del repositorio en un plan de desarrollo
local verificable. Su objetivo es evitar dos errores:

- confundir una app Django instalada con una funcionalidad terminada
- desarrollar pantallas o automatizaciones sin cerrar antes seguridad,
  ownership, lifecycle, auditoria y pruebas

La etapa vigente es local-first. El runtime soportado usa Django/DRF,
PostgreSQL, outboxes durables y workers locales. Los adapters cloud no forman
parte de los criterios de cierre actuales.

## Escala de madurez

| Nivel | Significado |
| --- | --- |
| Operativo | Tiene modelos, API o servicios, ownership, pruebas y un flujo utilizable. |
| Parcial | Resuelve parte del flujo, pero faltan lifecycle, integracion, soporte o pruebas. |
| Scaffold | La app y su README reservan una frontera; no debe presentarse como funcionalidad activa. |

Un modulo solo se considera terminado cuando cubre:

1. flujo completo del usuario
2. autorizacion y aislamiento por propietario o membresia
3. estados y transiciones validas mediante servicios
4. idempotencia en escrituras reintentables
5. eventos/outbox cuando existen efectos posteriores al commit
6. vista de soporte segura y auditada cuando sea necesaria
7. pruebas de contrato, permisos y casos de error
8. documentacion y ejemplos Postman actualizados

## Viaje base del usuario

El recorrido inicial que debe funcionar antes de ampliar el producto es:

1. registro, verificacion y onboarding
2. creacion de cuenta financiera
3. captura manual, importada o inferida de una transaccion
4. confirmacion y materializacion en el ledger
5. clasificacion por categoria, vendor y contexto de presupuesto
6. seguimiento de presupuesto, deuda, pago programado o meta
7. generacion de alerta, notificacion y senal de actualizacion
8. investigacion por soporte con motivo, caso y auditoria

La interfaz puede sugerir clasificaciones. La API y los servicios de dominio
conservan la autoridad contable y de permisos.

## Evaluacion por contexto

### Identity y seguridad

| Modulo | Estado | Flujo de usuario | Flujo interno o de soporte | Siguiente cierre |
| --- | --- | --- | --- | --- |
| `identity.users` | Operativo | Registro, login, perfil, onboarding, recovery, MFA, plan y capacidades. | Suspender exige motivo, audita y revoca todas las familias. | Certificar canales externos antes de produccion. |
| `identity.devices` | Operativo | Registrar, probar clave, atestar y revocar dispositivos. | Soporte ve conteos y estados, nunca secretos del dispositivo. | Certificar Play Integrity/App Attest en hardware real. |
| `identity.sessions` | Operativo | Consultar y cerrar sesiones. | Password, dispositivo, suspension y riesgo critico revocan estado persistente. | Monitorear anomalias y ajustar umbrales con datos reales. |
| `identity.consents` | Operativo | Aceptar, consultar y retirar consentimientos versionados. | Cumplimiento reconstruye evidencia y teardown asociado. | Probar retiro idempotente y sus efectos por integracion. |
| `identity.permissions` | Parcial | Resolver capacidades y grants. | Staff explica por que una capacidad fue permitida o denegada. | Unificar explicabilidad, vigencia y auditoria de overrides. |
| `identity.eventing` | Operativo | Sin UI directa; proyecta uso y cambios de identidad. | Operacion inspecciona outbox y proyecciones. | Cobertura de replay, deduplicacion y dead letter local. |
| `identity.social_identities` | Parcial | Vincular o desvincular identidad externa. | Soporte revisa proveedor y estado sin tokens. | Cerrar reautenticacion, conflicto de cuentas y revocacion. |

### Finanzas y ledger

| Modulo | Estado | Flujo de usuario | Flujo interno o de soporte | Siguiente cierre |
| --- | --- | --- | --- | --- |
| `finance.accounts` | Operativo | Crear, compartir, sincronizar, congelar, archivar y cerrar cuentas. | Estado, membresias, sync, snapshots y outbox observables. | Endurecer reconciliacion y pruebas concurrentes de lifecycle. |
| `finance.transactions` | Operativo | CRUD manual, intake individual/lote, voz inferida, confirmacion y conciliacion. | Soporte inspecciona estados y correlacion sin alterar verdad contable manualmente. | Completar matriz de ownership en todas las relaciones y pruebas por rail. |
| `finance.categories` | Operativo basico | Crear categorias personales y usarlas al clasificar movimientos. | Soporte solo ve conteos; no necesita CRUD global. | Reglas de categorias del sistema frente a categorias personales. |
| `finance.vendors` | Operativo | Crear comercios, asociarlos y registrar aliases sugeridos por intake. | Soporte usa datos minimizados y auditados. | Revision humana para enlazar aliases; nunca autoconfirmar vendor. |
| `finance.budgets` | Operativo | Presupuesto personal/compartido y metricas planned/actual/committed. | El cierre mensual congela el overview dentro del snapshot versionado. | Pruebas concurrentes y politica de correccion posterior al cierre. |
| `finance.debts` | Operativo | Crear deuda, cuotas, pagos y reestructuracion idempotente sin borrar cuotas pagadas. | Soporte consulta lifecycle, outbox y snapshots before/after. | Casos avanzados de intereses, mora y refinanciacion multimoneda. |
| `finance.fx` | Operativo basico | Consultar tasas para vistas multimoneda. | Administracion carga o valida snapshots globales. | Definir fuente, vigencia, fallback y politica de correccion local. |
| `finance.investments` | Scaffold/modelo | Registrar posiciones y ver rendimiento. | Soporte explica fuente y corte de valuacion. | Definir aggregate, API, cotizaciones y pruebas antes de exponerlo. |
| `finance.limits` | Scaffold | Ver limites de producto y consumo. | Staff explica overrides y bloqueos. | Consolidar plan limits, seguridad y rate limits sin duplicar reglas. |

### Planning y compromisos

| Modulo | Estado | Flujo de usuario | Flujo interno o de soporte | Siguiente cierre |
| --- | --- | --- | --- | --- |
| `planning.goals` | Operativo | Metas, aportes idempotentes, reversos, milestones y proyeccion explicable. | Admin conserva aportes, hitos y outbox como evidencia. | Escenarios persistidos y rendimientos configurables. |
| `planning.milestones` | Reserva | La capacidad activa `GoalMilestone` vive en `planning.goals`. | El evento registra logro y reapertura. | Eliminar el scaffold o convertirlo en read model si aparece una necesidad separada. |
| `planning.projections` | Reserva | La proyeccion determinista vive como accion de la meta y no modifica ledger. | Expone supuestos y ventana observada. | Snapshots de escenarios comparables, sin duplicar el aggregate. |
| `planning.shared_goals` | Operativo basico | Compartir por team, aportar con cuenta propia y restringir a miembros o managers. | Revocacion explicita conserva trazabilidad. | Invitaciones especificas por meta y resolucion de disputas. |
| `payments.scheduled_payments` | Operativo | Crear template idempotente, materializar corrida y enlazar presupuesto/deuda. | Operacion inspecciona runs, retries y materializacion. | Completar UX de edicion/cancelacion y ampliar pruebas concurrentes. |
| `payments.reminders` | Scaffold | Recibir recordatorio configurable. | Soporte explica por que se envio o silencio. | Integrarlo con runs, preferencias y dedupe. |
| `payments.calendar` | Scaffold | Consultar compromisos por fecha. | Soporte filtra por origen y estado. | Crear read model desde templates, runs, deudas y metas. |

### Pagos externos

| Modulo | Estado | Flujo de usuario | Flujo interno o de soporte | Siguiente cierre |
| --- | --- | --- | --- | --- |
| `payments.payment_intents` | Operativo local | Crear intent, ejecutar `local_fake`, procesar callbacks ordenados, conciliar y materializar. | Operacion ve receipts, settlement y casos de reverso/disputa. | Validar Wompi sandbox con vectores oficiales antes de dinero real. |
| `integrations_stub.payments` | Legacy/adaptador | No es el fake canonico. | Desarrollo usa `payments.local_fake`. | Retirar cuando no tenga consumidores. |

El ledger vive en `finance.transactions`. `payments` representa ejecucion
externa y nunca debe convertirse en la fuente contable final.

### Social y colaboracion

| Modulo | Estado | Flujo de usuario | Flujo interno o de soporte | Siguiente cierre |
| --- | --- | --- | --- | --- |
| `contacts` | Operativo basico | Crear contactos financieros y consultar balance neto. | Soporte verifica ownership y referencias. | Dedupe, invitacion opcional y privacidad. |
| `social.teams` | Operativo basico | Crear equipo; las altas de miembros pasan por invitacion aceptada. | Soporte revisa roles y conflictos. | Matriz de permisos por accion y salida voluntaria del miembro. |
| `social.contacts` | Scaffold duplicado | No debe exponerse mientras `contacts` sea canonico. | N/A. | Decidir migracion o eliminacion para evitar dos fuentes. |
| `social.groups` | Scaffold | Agrupar personas para casos compartidos. | Soporte inspecciona ownership y membresias. | Definir diferencia exacta frente a teams. |
| `social.memberships` | Scaffold | Aceptar, cambiar rol o abandonar un grupo. | Soporte resuelve estados e invitaciones. | Modelo de autorizacion comun reutilizable. |
| `social.invitations` | Operativo basico | Enviar, abrir, aceptar y revocar invitaciones con rol y vencimiento. | Notificacion durable y trazabilidad de lifecycle. | Outbox contextual cuando existan mas consumidores. |
| `social.shared_expenses` | Scaffold | Dividir gasto, aceptar participacion y liquidar. | Soporte reconstruye partes, saldos y disputas. | Aggregate y ledger de settlement sin duplicar `TransactionParticipant`. |
| `social.chat` | Scaffold | Conversar sobre una operacion compartida. | Moderacion y soporte con acceso excepcional auditado. | Posponer hasta cerrar colaboracion financiera; alta carga de privacidad. |
| `social.documents_shared` | Scaffold | Compartir comprobantes con permisos explicitos. | Soporte inspecciona grants, no contenido por defecto. | Depende de Documents y de permisos de membresia. |

### Documentos

| Modulo | Estado | Flujo de usuario | Flujo interno o de soporte | Siguiente cierre |
| --- | --- | --- | --- | --- |
| `documents.files` | Operativo | Carga privada, cifrado, grant de descarga, borrado logico y purga con legal hold. | Soporte ve metadata y estado; nunca URL publica directa. | Definir retencion legal por jurisdiccion antes de produccion. |
| `documents.storage` | Parcial | Filesystem privado local sin diferencia visible para el usuario. | Operacion valida integridad mediante SHA-256. | Extraer adapter cuando exista un segundo backend de almacenamiento. |
| `documents.metadata` | Operativo | Pistas no autoritativas y correccion OCR versionada por campo. | Soporte compara lineage sin convertirlo en verdad contable. | Politica de merge entre OCR y correccion contable. |
| `documents.ocr_requests` | Operativo | Solicitar extraccion idempotente y ver progreso. | Worker durable recupera locks stale y emite outbox sin contenido sensible. | Incorporar motor OCR de imagen local y politicas de retry/dead letter. |
| `documents.links_to_transactions` | Operativo basico | Vincular comprobante a una transaccion propia. | Soporte valida ownership cruzado. | UX mobile de vinculacion y pruebas de lifecycle al borrar. |
| `integrations_stub.ocr` | Scaffold/adaptador | Simulacion local de OCR. | Desarrollo prueba respuestas y fallos. | Fake determinista antes de integrar un proveedor. |

### Alertas, notificaciones y actualizacion de UI

| Modulo | Estado | Flujo de usuario | Flujo interno o de soporte | Siguiente cierre |
| --- | --- | --- | --- | --- |
| `alerts.alerts` | Operativo | Consultar, reconocer, posponer y resolver alertas. | Operacion inspecciona origen, severidad, correlacion y dispatch IA. | Politicas de dedupe y expiracion por tipo. |
| `alerts.rules` | Parcial | Configurar reglas permitidas por plan. | Soporte explica activacion y evaluacion. | Motor de evaluacion local, versionado y pruebas de umbral. |
| `alerts.triggers` | Scaffold | Sin uso directo. | Operacion identifica el evento disparador. | Implementar solo si rules/listeners no cubren la responsabilidad. |
| `alerts.listeners` | Scaffold nominal | Sin API; los handlers reales viven hoy junto al dominio. | Operacion observa consumo y retries. | Consolidar ubicacion sin duplicar listeners. |
| `alerts.ai_stub` | Scaffold/adaptador | Enriquecimiento opcional, nunca autoridad financiera. | Operacion ve version y estado del job. | Fake local y contrato de explicabilidad. |
| `notifications.deliveries` | Operativo | Inbox persistente y marcar como leida. | Soporte consulta estados agregados. | Dedupe por evento/canal y retry de entregas. |
| `notifications.preferences` | Operativo | Activar o silenciar canales y tipos. | Soporte explica por que no se entrego. | Aplicar preferencias en todos los listeners. |
| `notifications.listeners` | Operativo parcial | Convierte eventos en items de inbox. | Operacion monitorea efectos por evento. | Matriz documentada de evento a notificacion. |
| `notifications.templates` | Scaffold | Mensajes consistentes por locale/canal. | Operacion versiona plantillas. | Introducir cuando exista mas de un canal real. |
| `realtime.consumers` | Parcial | Polling de senales para refrescar vistas. | Operacion inspecciona backlog y expiracion. | Contrato de cursor, ack y retencion; WebSocket no es prioridad. |

Para el volumen inicial de aproximadamente 1.000 usuarios no se requiere
Celery, Redis ni RabbitMQ. PostgreSQL, outbox y workers locales son suficientes
mientras se midan backlog, latencia, locks y retries. Realtime comienza con
polling incremental; un broker se agrega solo con evidencia de carga.

### Reportes y analitica

| Modulo | Estado | Flujo de usuario | Flujo interno o de soporte | Siguiente cierre |
| --- | --- | --- | --- | --- |
| `reports.reports` | Operativo basico | Agregados y snapshots filtrados por periodo, moneda y zona horaria. | Soporte reproduce hash, corte y version. | Cobertura multimoneda con conversion FX explicita. |
| `reports.summaries` | Scaffold | Ver resumen reutilizable. | Soporte identifica fuente y fecha. | Read model mensual derivado de ledger/budgets. |
| `reports.monthly_reports` | Operativo | Cerrar meses terminados y regenerar solo con motivo. | Versiones enlazadas y cierre actual unico por owner/mes/moneda. | Automatizacion opcional y aprobacion de correcciones. |
| `reports.snapshots` | Operativo | Foto inmutable con hash, as_of y lineage de version. | Soporte compara supersedes y motivo. | Politica de retencion legal por jurisdiccion. |
| `reports.exports` | Operativo | JSON/CSV cifrado, token de un uso, expiracion y purga criptografica. | Operacion ve estado sin leer contenido. | PDF, cuotas y pruebas de archivos grandes. |

### Soporte, administracion y operacion

| Modulo | Estado | Flujo interno | Controles obligatorios | Siguiente cierre |
| --- | --- | --- | --- | --- |
| `support.audit` | Operativo | Consultar evidencia funcional por usuario, modulo o entidad. | Inmutabilidad practica, minimizacion y acceso staff. | Correlacion por request/event y politica de retencion. |
| `admin_tools.user_lookup` | Operativo basico | Buscar usuario y ver resumen 360 de estados/conteos. | Staff, motivo obligatorio, caso opcional y auditoria `READ`; sin montos. | Integrarlo a un panel interno y agregar links controlados a casos. |
| `support.access_history` | Operativo basico | Registra acceso staff a timeline Open Banking con motivo y caso. | Nunca registra secretos o payload financiero crudo. | Aplicarlo a documentos, pagos y reportes sensibles. |
| `support.consent_audit` | Scaffold | Revisar historial legal de consentimiento. | Evidencia versionada y no mutable. | Proyeccion dedicada sobre `identity.consents`. |
| `support.support_views` | Scaffold | Vistas agregadas de casos. | Least privilege y acceso auditado. | Definir solo tras validar necesidades reales del equipo. |
| `admin_tools.dashboards` | Operativo basico | Snapshot interno de outboxes, OCR, scheduler, notificaciones y pagos. | Endpoint staff-only, agregado y auditado. | Construir UI interna, filtros por request/event y alertas de umbral. |
| `admin_tools.manual_adjustments` | Scaffold de alto riesgo | Correcciones excepcionales. | Doble confirmacion, motivo, diff, idempotencia y auditoria alta. | No implementar hasta definir politica contable. |
| `admin_tools.alert_review` | Scaffold | Revisar alertas criticas o IA. | Separar lectura de intervencion. | Cola de revision y decisiones auditadas. |
| `admin_tools.audit_trails` | Scaffold | Navegar trazas relacionadas. | Lectura staff y minimizacion. | Read model sobre `support.audit`, no segunda fuente. |

### Runtime, integraciones y observabilidad

| Modulo | Estado | Responsabilidad actual | Siguiente cierre |
| --- | --- | --- | --- |
| `tasks.workers` | Operativo | Runner comun de jobs durables locales. | Registro declarativo de nuevos jobs y metricas uniformes. |
| `tasks.scheduled` | Operativo | Scheduler local singleton con advisory locks y estado durable. | Ampliar catalogo solo con jobs que tengan owner, idempotencia y metricas. |
| `tasks.listeners` | Scaffold | Frontera tecnica de listeners. | Evitar duplicar handlers de dominio existentes. |
| `tasks.dispatchers` | Parcial | Seleccion de backend async por runtime. | Mantener local como backend efectivo; cloud deshabilitado. |
| `observability` | Operativo | Health/readiness, logs JSON y status commands. | Metricas de latencia, errores y backlog con umbrales. |
| `integrations.open_banking` | Operativo local/contractual | Contrato v1, catalogo institucional, cuarentena, sync paginado, retries, reconcile y timeline. | La compuerta de checksum mantiene sandbox real bloqueado hasta certificar payloads y firmas oficiales. |
| `integrations_stub.banks` | Parcial/adaptador | Ejecuta simulaciones/jobs delegados; no conserva lifecycle de conexion. | Mantener fake determinista y no duplicar `integrations.open_banking`. |
| `integrations_stub.llm` | Parcial/adaptador | Contrato local para inferencia. | Separar extraccion de clasificacion y registrar version. |
| `integrations_stub.ml` | Scaffold | Frontera de modelos predictivos. | No activar sin dataset, metrica y fallback explicito. |

## Orden de implementacion

### P0. Seguridad multiusuario

Fundacion transversal completada en esta iteracion:

- redirect de reset allowlisted y respuestas anti-enumeracion
- throttling PostgreSQL en login, recovery y Open Banking webhooks
- llaves separadas para Django, JWT, recovery, throttle y cifrado
- envelope encryption AES-256-GCM y `IntegrationCredential`
- metadata segura, masking, redaccion de logs y auditoria
- JWT ligado a estado persistido de sesion
- webhook con timestamp, tolerancia, HMAC e idempotencia
- comandos `security_status`, `key_rotation_status` y worker de rewrap
- escaneo de secretos en CI y hardening inicial Flutter
- catalogo de politica para todos los JSON actuales y auditoria estricta de API
- retencion automatizada de eventos, throttling, challenges y grants vencidos
- MFA TOTP/recovery codes, JWT multi-key y lifecycle de attestation

Siguiente auditoria transversal, fuera del cierre de estos siete frentes:

- auditar todos los `ModelViewSet` y serializers relacionales
- garantizar querysets por owner/membership
- asignar owner desde `request.user`
- rechazar relaciones cruzadas entre usuarios

Categorias, vendors, deudas/cuotas y metas ya tienen cobertura inicial.

La infraestructura de Play Integrity y App Attest esta implementada, pero la
certificacion end-to-end permanece bloqueada por credenciales y hardware reales.
El pinning mobile ya exige pin activo y respaldo; ingresar pins reales y probar
su rotacion sigue siendo una compuerta de release. El keyring local fue
ejercitado con rotacion y retiro real; no se versiona una llave de ejemplo.

### P1. Plano de soporte

- vista 360 minimizada y auditada
- acciones administrativas con motivo, caso y diff
- dashboard de outboxes, workers, errores y locks stale

La vista 360 inicial ya esta disponible en `/api/internal/support/users/`.

### P2. Ciclos financieros incompletos

- deuda/cuota con servicios explicitos y eventos: completado
- progreso/aportes de metas: completado
- ejecucion local periodica de pagos programados: completado
- revision de ownership en payment intents y shared budgets: completado

P2 queda cerrado. `scheduler-local` coordina vencimientos y pagos programados
con advisory lock y estado durable. Payment intents aisla referencias e
idempotencia por owner; shared budgets aplica permisos por membresia y el BFF
mobile versiona tambien presupuestos visibles para miembros.

### P3. Documentos locales

- carga segura al filesystem local
- metadata y checksum
- OCR fake + worker durable
- vinculacion atomica a transacciones

Completado ademas: cifrado, grants de un uso, retencion/purga, legal hold,
correccion OCR con lineage y ClamAV local validado con EICAR. El keyring local
se ejercito con `v1 -> v2`, rewrap, respaldo DPAPI, restauracion y retiro seguro
de `v1`. Produccion debera usar custodia externa y doble control.

### P4. Finanzas compartidas

- autorizacion comun por membresia
- invitaciones idempotentes
- gastos compartidos y settlement
- metas compartidas

Metas compartidas ya cubren membresia, politica de aportes y ownership por
contribuyente. Gastos compartidos y settlement siguen pendientes.

### P5. Reportes y exportaciones

- cierres reproducibles
- snapshots versionados
- export asincrono local
- descarga autorizada y expirable

Completado para JSON/CSV: cierre, regeneracion con motivo, snapshots inmutables,
cifrado, descarga de un uso y purga. Pendiente: PDF y politica legal definitiva.

### P6. Proveedores externos

Solo despues de estabilizar contratos locales se conectan bancos, pagos, OCR o
IA reales. El adapter cambia; dominio, idempotencia, auditoria y pruebas no.

## Signals, servicios y outbox

- los services ejecutan casos de uso y transiciones de negocio
- `transaction.atomic()` protege cambios que deben confirmarse juntos
- `transaction.on_commit()` inicia efectos solo despues del commit
- el outbox persiste efectos que deben sobrevivir reinicios y reintentos
- los workers procesan fuera del request path con idempotencia y locks
- los signals se reservan para invariantes tecnicas pequenas, no para
  orquestaciones financieras invisibles

Agregar una caracteristica no debe exigir registrar archivos por entorno. Se
declara su contrato de dominio y, si necesita trabajo durable, su job en el
catalogo comun. El runtime local lo ejecuta con el mismo entrypoint operativo.
