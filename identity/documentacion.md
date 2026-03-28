# Documentacion De Identity

Este documento explica el bounded context `identity.users` despues de su
alineacion con `finance.accounts`, el bus de eventos y la arquitectura cloud de
Vexxo.

## 1. Proposito Del Modulo
`identity.users` ya no se entiende solo como autenticacion. Ahora es el origen
del lifecycle del usuario dentro de Vexxo.

En lenguaje tecnico:
- define identidad, estado operativo, plan, moneda preferida, onboarding y
  preferencias base del usuario
- publica eventos de dominio cuando cambia el lifecycle del usuario
- implementa autenticacion social OAuth2 para Google y Facebook con handoff seguro
- coordina onboarding sin crear directamente recursos de otros bounded contexts

En lenguaje simple:
- aqui nace el usuario
- aqui se sabe si esta activo, suspendido o verificado
- aqui se conoce su plan y su moneda base
- desde aqui se disparan las acciones que crean su espacio financiero

## 2. Mapa De Carpetas
- [identity/users/models](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/models)
  Contiene el modelo `User`.
- [identity/users/domain](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/domain)
  Contiene matriz de planes y contrato de eventos.
- [identity/users/services](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services)
  Contiene publicacion de eventos, bootstrap interno y preparacion OAuth.
- [identity/users/signals.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/signals.py)
  Detecta cambios relevantes del usuario y publica eventos.
- [identity/users/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/event_handlers.py)
  Escucha eventos de usuario y materializa defaults internos.
- [identity/users/serializers](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/serializers)
  Define registro, perfil y admin.
- [identity/users/views](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views)
  Expone auth, onboarding, dashboard y admin.
- [identity/users/urls.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/urls.py)
  Publica las rutas del contexto.

## 3. Modelo `User`
Archivo:
- [identity/users/models/user.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/models/user.py)

Responsabilidades actuales del modelo:
- identidad base: `username`, `email`, `first_name`, `last_name`
- preferencias: `preferred_currency`, `timezone_name`, `locale`
- lifecycle: `status`, `is_active`, `is_verified`, `onboarding_completed`
- plan comercial: `plan`
- observabilidad minima: `last_seen`, `last_login_ip`
- overrides operativos: limites manuales por soporte/admin

Helpers importantes:
- `display_name`
- `full_name()`
- `is_premium`
- `get_plan_config()`
- `can_create_account()`
- `can_add_investment_account()`
- `can_add_api_connection()`
- `can_add_contact()`
- `can_generate_monthly_report()`

## 4. Politica Canonica De Planes
Archivo:
- [identity/users/domain/plan_matrix.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/domain/plan_matrix.py)

Decision arquitectonica:
- `User.plan` es la fuente oficial del plan del usuario
- la matriz de capacidades vive en `identity.users.domain.plan_matrix`
- `finance.accounts` ahora consume esa misma matriz

Ejemplo tecnico:
```python
get_plan_capabilities("free")
```

Ejemplo de salida:
```python
{
    "plan": "free",
    "max_accounts": 3,
    "max_active_accounts": 3,
    "max_primary_accounts": 1,
    "max_investment_accounts": 1,
    "max_api_connections": 1,
    "max_contacts": 2,
}
```

En lenguaje simple:
- el usuario free, plus o pro ya no tiene una regla en `users` y otra distinta
  en `accounts`
- ambos leen la misma politica

## 5. Registro, Login Y Perfil
Archivos:
- [identity/users/serializers/user_serializer.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/serializers/user_serializer.py)
- [identity/users/views/auth.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views/auth.py)

### 5.1. Registro
Endpoint:
- `POST /api/identity/users/auth/register/`

Contrato esperado:
- `full_name`
- `email`
- `password`
- `password2`
- opcionalmente `preferred_currency`, `timezone_name`, `locale`, `phone_number`

Que hace por dentro:
1. valida contrasenas
2. divide `full_name` en `first_name` y `last_name`
3. genera `username` interno automaticamente
4. normaliza `email`
5. asigna plan `free`
6. deja `status=active`
7. guarda el usuario
8. los signals publican `users.registered.v1`

Ejemplo simple:
```json
{
  "full_name": "Ada Lovelace",
  "email": "ada@example.com",
  "password": "VexxoPass2026!",
  "password2": "VexxoPass2026!"
}
```

### 5.2. Login
Endpoint:
- `POST /api/identity/users/auth/login/`

Permite:
- username + password
- email + password

JWT claims relevantes:
- `username`
- `email`
- `plan`
- `status`
- `base_currency`
- `display_name`
- `onboarding_completed`

### 5.3. Perfil
Endpoint:
- `GET /api/identity/users/me/`
- `PUT /api/identity/users/me/`
- `PATCH /api/identity/users/me/`

Permite editar:
- `full_name`
- `phone_number`
- `preferred_currency`
- `timezone_name`
- `locale`

Cuando cambia `preferred_currency`, el sistema emite
`users.currency.changed.v1` y `accounts` sincroniza la moneda base de cuentas
compatibles.

### 5.4. Onboarding
Endpoint:
- `POST /api/identity/users/onboarding/complete/`

Que hace:
- marca `onboarding_completed=True`
- dispara `users.onboarding.completed.v1` via signals

## 6. OAuth2 Social Operativo Con Handoff Seguro
Archivo:
- [identity/users/services/oauth_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/oauth_service.py)

Endpoints:
- `GET /api/identity/users/auth/social/providers/`
- `GET /api/identity/users/auth/social/google/start/`
- `GET /api/identity/users/auth/social/facebook/start/`

Estado actual:
- si intercambia `code -> token` contra Google/Facebook cuando existen credenciales
- si autentica o vincula identidades sociales contra proveedores reales
- usa modelo `frontend callback + backend exchange + backend emite eventos`
- mantiene `GET /callback/` como compatibilidad, pero el camino principal es:
  - el frontend recibe `code` y `state`
  - el frontend llama `POST /auth/social/exchange/`
  - el backend hace el exchange real, crea o vincula usuario, registra sesion/dispositivo y publica eventos

En lenguaje simple:
- el backend ya sabe que Google y Facebook existen como proveedores
- ya sabe si estan configurados
- ya sabe a donde deberian redirigir
- cuando pongas las credenciales reales, el flujo ya puede autenticar y vincular identidades sociales de punta a punta

## 7. Eventos De `identity.users`
Archivos:
- [identity/users/domain/events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/domain/events.py)
- [common/domain_events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/common/domain_events.py)

Eventos actuales:
- `users.registered.v1`
- `users.profile.updated.v1`
- `users.plan.changed.v1`
- `users.currency.changed.v1`
- `users.onboarding.completed.v1`
- `users.verified.v1`
- `users.suspended.v1`
- `users.activated.v1`
- `users.social_auth.prepared.v1`

Como se generan:
1. `pre_save` guarda estado previo
2. `post_save` detecta cambios semanticos
3. `identity.users.services.event_service.publish_user_event_after_commit()`
   publica al bus despues del commit

Que escucha que:
- `users.registered.v1`
  - `identity.users.event_handlers.handle_user_registered()`
  - `finance.accounts.event_handlers.handle_user_registered()`
- `users.plan.changed.v1`
  - `finance.accounts.event_handlers.handle_user_plan_changed()`
- `users.currency.changed.v1`
  - `finance.accounts.event_handlers.handle_user_currency_changed()`
- `users.suspended.v1`
  - `finance.accounts.event_handlers.handle_user_suspended()`
- `users.activated.v1`
  - `finance.accounts.event_handlers.handle_user_activated()`
- `users.onboarding.completed.v1`
  - `identity.users.event_handlers.handle_user_onboarding_completed()`

## 8. Relacion Con `finance.accounts`
Archivos importantes:
- [finance/accounts/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/event_handlers.py)
- [finance/accounts/services/user_integration_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/user_integration_service.py)

Relaciones activas:
- `users.registered.v1` -> crea la cuenta base del usuario
- `users.plan.changed.v1` -> refresca proyecciones de cuentas
- `users.currency.changed.v1` -> sincroniza `base_currency` de cuentas elegibles
- `users.suspended.v1` -> desactiva auto-sync en cuentas externas
- `users.activated.v1` -> refresca inteligencia de cuentas

Ejemplo entendible:
- el usuario cambia su moneda preferida de `COP` a `USD`
- `users` emite `users.currency.changed.v1`
- `accounts` escucha ese evento
- las cuentas del usuario cuya moneda base seguia la preferencia anterior pasan
  a usar `USD`
- luego se recalculan snapshots/inteligencia

## 9. Bootstrap Del Usuario
Archivo:
- [identity/users/services/bootstrap_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/bootstrap_service.py)

Bootstrap actual:
- categorias base
- equipo personal
- alertas de bienvenida

Lo que NO hace ya directamente:
- crear cuentas financieras

Eso ahora pertenece a `accounts`.

## 10. Dashboard
Archivo:
- [identity/users/views/dashboard.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views/dashboard.py)

Cambio importante:
- ya no se apoya solo en queries planas y supuestos viejos
- intenta reutilizar:
  - `AccountOwnerMetrics`
  - `AccountPortfolioSnapshot`
  - `AccountRiskSnapshot`

Si no existen aun:
- intenta primero refresco asincrono de proyecciones; solo hace fallback local cuando la configuracion del entorno lo permite

Eso alinea el dashboard con el bounded context `accounts`.

## 11. Configuracion GCP Y OAuth
Archivos:
- [.env](/c:/Users/Alamb/Documents/Vexxo_Backend_API/.env)
- [backend/settings.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/backend/settings.py)

Variables nuevas:
- `GCP_IDENTITY_PLATFORM_ENABLED`
- `GCP_IDENTITY_PLATFORM_PROJECT_ID`
- `GCP_IDENTITY_PLATFORM_TENANT_ID`
- `GCP_IDENTITY_PLATFORM_API_KEY`
- `GOOGLE_OAUTH_ENABLED`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_CALLBACK_URL`
- `FACEBOOK_OAUTH_ENABLED`
- `FACEBOOK_OAUTH_CLIENT_ID`
- `FACEBOOK_OAUTH_CLIENT_SECRET`
- `FACEBOOK_OAUTH_CALLBACK_URL`

Que hay que rellenar para habilitar social login con proveedores reales:
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_CALLBACK_URL`
- `FACEBOOK_OAUTH_CLIENT_ID`
- `FACEBOOK_OAUTH_CLIENT_SECRET`
- `FACEBOOK_OAUTH_CALLBACK_URL`

Si usas GCP Identity Platform mas adelante:
- `GCP_IDENTITY_PLATFORM_ENABLED=True`
- `GCP_IDENTITY_PLATFORM_PROJECT_ID=<tu proyecto>`
- `GCP_IDENTITY_PLATFORM_TENANT_ID=<tenant si aplica>`
- `GCP_IDENTITY_PLATFORM_API_KEY=<api key del flujo>`

## 12. Flujo Completo Del Usuario
### 12.1. Registro
1. frontend envia nombre completo, correo y contrasena
2. `UserRegisterSerializer` crea `User`
3. `users.signals` emite `users.registered.v1`
4. `users.event_handlers` crea categorias, equipo y alertas
5. `accounts.event_handlers` crea la cuenta principal y refresca portfolio

### 12.2. Cambio De Moneda Preferida
1. usuario hace `PATCH /me/`
2. cambia `preferred_currency`
3. signal emite `users.currency.changed.v1`
4. `accounts` alinea cuentas elegibles
5. se refresca inteligencia

### 12.3. Cambio De Plan
1. admin cambia plan via API
2. signal emite `users.plan.changed.v1`
3. `accounts` refresca su proyeccion y valida con la misma matriz canonica

### 12.4. Suspension
1. admin suspende usuario
2. `status=suspended` e `is_active=False`
3. signal emite `users.suspended.v1`
4. `accounts` desactiva auto-sync para cuentas externas del owner

## 13. Estado Actual Y Siguiente Paso
Ya resuelto:
- registro coherente con nombre completo + email + password
- plan canonico compartido con `accounts`
- bootstrap por eventos
- social OAuth operativo con handoff seguro
- dashboard alineado con inteligencia de cuentas
- documentacion y contrato de eventos del contexto

Pendiente para una siguiente iteracion:
- email verification real
- MFA / step-up auth mas fuerte
- Identity Platform o broker social administrado si decides externalizar auth

## 14. Dispositivos, Sesiones, Consentimientos Y Permisos

### 14.1. Vision General
Estas cuatro apps extienden identidad hacia seguridad, trazabilidad y gobierno
de acceso:
- `identity.devices`: representa dispositivos conocidos del usuario
- `identity.sessions`: representa sesiones/autenticaciones concretas
- `identity.consents`: representa consentimiento legal o regulatorio
- `identity.permissions`: representa grants de producto/feature access

En conjunto sirven para:
- metadata de login y actividad
- soporte y seguridad operativa
- consentimiento para open banking y data sharing
- activaciones beta, enterprise overrides y permisos contextuales

### 14.2. Dispositivos
Archivos:
- [identity/devices/models](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/devices/models)
- [identity/devices/models/device.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/devices/models/device.py)
- [identity/devices/serializers](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/devices/serializers)
- [identity/devices/serializers/device_serializers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/devices/serializers/device_serializers.py)
- [identity/devices/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/devices/services.py)
- [identity/devices/views](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/devices/views)
- [identity/devices/views/device_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/devices/views/device_views.py)

Entidad principal:
- `UserDevice`

Campos clave:
- `fingerprint`
- `external_device_id`
- `device_type`
- `platform`
- `os_version`
- `app_version`
- `push_token`
- `trust_level`
- `first_seen_at`
- `last_seen_at`
- `metadata`

Endpoints:
- `GET /api/identity/devices/dispositivos/`
- `POST /api/identity/devices/dispositivos/`
- `POST /api/identity/devices/dispositivos/register_device/`
- `POST /api/identity/devices/dispositivos/{id}/trust_device/`
- `POST /api/identity/devices/dispositivos/{id}/revoke/`
- `GET /api/identity/devices/dispositivos/suspicious/`
- `GET /api/identity/devices/dispositivos/summary/`

Relacion con login:
- cuando hay login, el backend intenta registrar/actualizar el dispositivo
  usando fingerprint y metadata tecnica si vienen en el request

Observabilidad agregada:
- `summary` devuelve total, activos, confiables, sospechosos, primarios y
  distribucion por tipo/trust level
- esta vista sirve para soporte, paneles de seguridad y trazabilidad de acceso

### 14.3. Sesiones
Archivos:
- [identity/sessions/models](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/models)
- [identity/sessions/models/session.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/models/session.py)
- [identity/sessions/serializers](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/serializers)
- [identity/sessions/serializers/session_serializers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/serializers/session_serializers.py)
- [identity/sessions/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/services.py)
- [identity/sessions/views](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/views)
- [identity/sessions/views/session_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/views/session_views.py)
- [identity/sessions/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/event_handlers.py)

Entidad principal:
- `UserSession`

Campos clave:
- `session_key`
- `refresh_jti`
- `access_jti`
- `session_type`
- `status`
- `provider`
- `device`
- `ip_address`
- `user_agent`
- `authenticated_at`
- `last_seen_at`
- `revoked_at`

Endpoints:
- `GET /api/identity/sessions/sesiones/`
- `GET /api/identity/sessions/sesiones/active/`
- `POST /api/identity/sessions/sesiones/register_session/`
- `POST /api/identity/sessions/sesiones/{id}/revoke/`
- `POST /api/identity/sessions/sesiones/{id}/touch/`
- `POST /api/identity/sessions/sesiones/revoke_all/`
- `GET /api/identity/sessions/sesiones/summary/`

Relacion con auth:
- login JWT registra `UserSession`
- logout intenta revocarla usando `refresh_jti`

Integracion por eventos:
- `users.suspended.v1` -> revoca sesiones activas del usuario
- `users.device.revoked.v1` -> revoca sesiones asociadas a ese dispositivo

Valor operativo:
- permite cortar acceso sin borrar historial
- prepara auditoria, soporte y step-up auth futuro

### 14.4. Consentimientos
Archivos:
- [identity/consents/models](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/models)
- [identity/consents/models/consent.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/models/consent.py)
- [identity/consents/serializers](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/serializers)
- [identity/consents/serializers/consent_serializers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/serializers/consent_serializers.py)
- [identity/consents/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/services.py)
- [identity/consents/views](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/views)
- [identity/consents/views/consent_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/views/consent_views.py)
- [identity/consents/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/event_handlers.py)

Entidad principal:
- `UserConsent`

Casos cubiertos:
- terminos
- privacidad
- marketing
- open banking data
- open banking payments
- export de datos
- OCR documental
- AI processing

Campos clave:
- `consent_type`
- `provider`
- `external_consent_id`
- `scope_code`
- `status`
- `purpose`
- `legal_basis`
- `terms_version`
- `privacy_version`
- `granted_at`
- `revoked_at`
- `expires_at`
- `data_categories`

Endpoints:
- `GET /api/identity/consents/consentimientos/`
- `POST /api/identity/consents/consentimientos/`
- `POST /api/identity/consents/consentimientos/grant/`
- `POST /api/identity/consents/consentimientos/{id}/revoke/`
- `GET /api/identity/consents/consentimientos/active/`
- `GET /api/identity/consents/consentimientos/expiring/`
- `GET /api/identity/consents/consentimientos/summary/`

Uso esperado en open banking:
- guardar el consentimiento de acceso a datos
- guardar `provider`
- guardar `external_consent_id`
- guardar alcance en `scope_code`
- guardar expiracion y revocacion

Integracion con `finance.accounts`:
- cuando se otorga un consentimiento, `accounts` refresca proyecciones del
  usuario porque cambia su capacidad de integracion
- cuando se revoca un consentimiento de open banking, se desactiva `allow_auto_sync`
  en cuentas externas del proveedor afectado

En lenguaje simple:
- si el usuario quita permiso a Belvo o al proveedor que usemos
- Vexxo deja de sincronizar automaticamente esas cuentas
- pero no pierde el historial de lo que ya existia

### 14.5. Grants De Permisos
Archivos:
- [identity/permissions/models](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/models)
- [identity/permissions/models/permission_grant.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/models/permission_grant.py)
- [identity/permissions/serializers](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/serializers)
- [identity/permissions/serializers/permission_serializers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/serializers/permission_serializers.py)
- [identity/permissions/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/services.py)
- [identity/permissions/views](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/views)
- [identity/permissions/views/permission_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/views/permission_views.py)
- [identity/permissions/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/event_handlers.py)

Entidad principal:
- `UserPermissionGrant`

Que resuelve:
- permisos de negocio mas ricos que los permisos nativos de Django
- grants manuales de soporte
- overrides enterprise
- feature access por scope

Campos clave:
- `permission_code`
- `scope_type`
- `scope_id`
- `status`
- `source`
- `granted_by`
- `expires_at`

Endpoints:
- `GET /api/identity/permissions/grants/`
- `POST /api/identity/permissions/grants/`
- `POST /api/identity/permissions/grants/{id}/revoke/`
- `GET /api/identity/permissions/grants/mine/`
- `GET /api/identity/permissions/grants/summary/`
- `GET /api/identity/permissions/grants/effective/`

Integracion automatica:
- `users.registered.v1` y `users.plan.changed.v1` sincronizan grants derivados
  del plan
- `users.consent.granted.v1` y `users.consent.revoked.v1` sincronizan grants
  derivados de consentimiento

Ejemplos de grants derivados:
- `accounts.extended.enabled`
- `accounts.multi_primary.enabled`
- `integrations.multi_connection.enabled`
- `consents.open_banking_data.enabled`
- `consents.ai_processing.enabled`

### 14.6. Eventos Nuevos Del Contexto
Eventos agregados:
- `users.device.registered.v1`
- `users.device.trusted.v1`
- `users.device.revoked.v1`
- `users.session.started.v1`
- `users.session.revoked.v1`
- `users.consent.granted.v1`
- `users.consent.revoked.v1`
- `users.permission.granted.v1`
- `users.permission.denied.v1`
- `users.permission.revoked.v1`

Estos eventos hoy sirven para:
- auditoria
- seguridad
- integraciones futuras
- analytics

Ahora tambien sirven para:
- revocar sesiones por suspension o por dispositivo revocado
- sincronizar permisos derivados por plan o consentimiento
- cortar auto-sync de cuentas externas cuando se revoca open banking

Flujo tecnico resumido:
1. una vista o servicio de `devices`, `sessions`, `consents` o `permissions`
   ejecuta una accion
2. se usa `publish_user_event_after_commit()`
3. el evento entra al bus de [common/domain_events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/common/domain_events.py)
4. listeners locales reaccionan
5. si el bootstrap global esta activo, el mismo evento tambien puede salir por
   Pub/Sub mediante la infraestructura ya preparada

Eso significa:
- identidad no queda aislada
- sus cambios ya tienen impacto operativo real en seguridad, cuentas y grants

### 14.7. Relacion Con La Vision De Vexxo
Estas apps refuerzan la arquitectura general:
- `devices` y `sessions` mejoran seguridad y observabilidad en Cloud Run/API Gateway
- `consents` prepara open banking, data integrations y cumplimiento
- `permissions` prepara enterprise, feature flags y soporte operativo

Relacion con GCP y arquitectura cloud:
- `Identity Platform` y OAuth social quedan como capa de autenticacion
- `Cloud Run` expone estas APIs de identidad
- `Pub/Sub` puede transportar estos eventos si el dispatcher global esta
  habilitado
- `Cloud Logging` y `Cloud Monitoring` pueden observar suspensiones, revocaciones
  y consentimientos desde los listeners
- `Secret Manager` y `KMS` siguen siendo el lugar natural para secretos OAuth
  o tokens de integraciones reales

Relacion con `accounts`:
- `users` gobierna lifecycle y estado del owner
- `consents` gobierna si ciertas integraciones financieras pueden seguir vivas
- `permissions` expresa capacidades comerciales/operativas derivadas
- `sessions` y `devices` cierran la parte de seguridad y trazabilidad de acceso

No reemplazan `users`.
Lo complementan.

## 15. Hardening Reciente De Identity

### 15.1. Outbox Persistente Del Contexto
Archivos:
- [identity/eventing/models.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/models.py)
- [identity/eventing/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/services.py)
- [identity/users/services/event_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/event_service.py)

Actualizacion importante:
- antes `identity` publicaba eventos solo con `transaction.on_commit`
- ahora usa `IdentityDomainEventOutbox`
- eso alinea `users`, `devices`, `sessions`, `consents` y `permissions` con el
  mismo patron de confiabilidad de `finance.accounts`

Flujo tecnico actualizado:
1. una vista, signal o servicio de `identity` construye el payload
2. `publish_user_event_after_commit()` delega en `identity.eventing`
3. se persiste `IdentityDomainEventOutbox`
4. al `commit`, el outbox publica al bus local
5. listeners locales reaccionan
6. si el bootstrap global esta habilitado, el evento tambien puede salir por
   Pub/Sub

En lenguaje simple:
- primero se guarda el hecho
- luego se publica
- si algo falla, el evento no se pierde silenciosamente

### 15.2. OAuth Social Ya Operativo
Archivos:
- [identity/social_identities/models.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/social_identities/models.py)
- [identity/users/services/oauth_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/oauth_service.py)
- [identity/users/views/auth.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views/auth.py)
- [identity/users/urls.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/urls.py)

Endpoints nuevos o ampliados:
- `GET /api/identity/users/auth/social/providers/`
- `GET /api/identity/users/auth/social/{provider}/start/`
- `GET /api/identity/users/auth/social/{provider}/callback/`
- `POST /api/identity/users/auth/social/exchange/`
- `GET /api/identity/users/auth/social/identities/`
- `DELETE /api/identity/users/auth/social/{provider}/unlink/`

Que hace ahora:
- genera `state` firmado y con expiracion
- construye authorization URL real
- intercambia `code` por token
- consulta perfil remoto de Google o Facebook
- decide si debe:
  - iniciar sesion con identidad ya vinculada
  - vincular el proveedor a un usuario autenticado
  - crear un usuario nuevo
  - bloquear auto-merge inseguro por email si no esta habilitado

Eventos nuevos:
- `users.social_auth.prepared.v1`
- `users.social_identity.linked.v1`
- `users.social_identity.unlinked.v1`

Regla de seguridad importante:
- si ya existe un usuario con ese email, no se enlaza automaticamente salvo que
  `IDENTITY_SOCIAL_AUTO_LINK_BY_EMAIL=True`
- la forma segura por defecto es: iniciar sesion primero y luego vincular

### 15.3. Endurecimiento De Sesiones
Archivos:
- [identity/sessions/models/session.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/models/session.py)
- [identity/sessions/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/services.py)
- [identity/sessions/views/session_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/views/session_views.py)
- [identity/sessions/serializers/session_serializers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/sessions/serializers/session_serializers.py)

Campos nuevos de `UserSession`:
- `family_id`
- `previous_refresh_jti`
- `risk_level`
- `requires_step_up`
- `last_refreshed_at`
- `refresh_rotated_at`

Capacidades nuevas:
- rotacion segura de refresh token
- deteccion basica de reuse
- revocacion por familia de sesion
- limite de sesiones activas por usuario
- step-up sugerido si el dispositivo es desconocido o sospechoso

Endpoints nuevos:
- `POST /api/identity/users/auth/refresh/`
- `POST /api/identity/sessions/sesiones/revoke_others/`
- `POST /api/identity/sessions/sesiones/revoke_family/`

Ejemplo simple:
- el usuario inicia sesion desde un celular nuevo
- el sistema registra el `UserDevice`
- la sesion nace con `risk_level=medium` o `high`
- `requires_step_up=True` si la politica del dispositivo lo exige

### 15.4. Consentimientos Y Ciclo De Integracion
Archivos:
- [identity/consents/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/event_handlers.py)
- [finance/accounts/services/user_integration_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/user_integration_service.py)
- [integrations_stub/banks/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/services.py)
- [integrations_stub/banks/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/views.py)

Mejora principal:
- revocar open banking ya no solo desactiva `allow_auto_sync`
- ahora tambien:
  - limpia `next_sync_at`
  - limpia `sync_cursor`
  - marca metadata de integracion revocada
  - deja un punto interno de teardown hacia integraciones

Endpoint interno nuevo:
- `POST /internal/integrations/banks/consents/revoke/`

Esto prepara el camino para que el futuro `integrations_service` haga:
- revocacion de tokens externos
- cierre de webhooks
- cancelacion de jobs pendientes
- bloqueo legal de nuevos fetches

### 15.5. Permisos: Grants Manuales Vs Entitlements
Archivos:
- [identity/permissions/models/permission_grant.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/models/permission_grant.py)
- [identity/permissions/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/services.py)

Campo nuevo:
- `grant_kind`

Valores:
- `manual`
- `entitlement`
- `override`

Decision de diseno:
- grants por plan o consentimiento ya no quedan mezclados conceptualmente con
  grants manuales de soporte o admin
- el modelo sigue siendo uno solo, pero la semantica ya esta separada

### 15.6. Configuracion GCP Y Variables Nuevas
Variables nuevas en [.env](/c:/Users/Alamb/Documents/Vexxo_Backend_API/.env):
- `IDENTITY_SOCIAL_STATE_SALT`
- `IDENTITY_SOCIAL_STATE_MAX_AGE_SECONDS`
- `IDENTITY_SOCIAL_AUTO_LINK_BY_EMAIL`
- `IDENTITY_MAX_ACTIVE_SESSIONS`
- `IDENTITY_STEP_UP_ON_UNKNOWN_DEVICE`
- `IDENTITY_STEP_UP_ON_SUSPICIOUS_DEVICE`
- `IDENTITY_STEP_UP_REQUIRED_PATHS`
- `IDENTITY_PROJECTIONS_LOCAL_FALLBACK_ENABLED`
- `IDENTITY_CONSENT_TEARDOWN_HANDLER_URL`
- `IDENTITY_CONSENTS_INTERNAL_TOKEN`
- `IDENTITY_CONSENT_LOCAL_FALLBACK_ENABLED`

Que debes rellenar para activar social login real:
- `GOOGLE_OAUTH_ENABLED=True`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_CALLBACK_URL`
- `FACEBOOK_OAUTH_ENABLED=True`
- `FACEBOOK_OAUTH_CLIENT_ID`
- `FACEBOOK_OAUTH_CLIENT_SECRET`
- `FACEBOOK_OAUTH_CALLBACK_URL`

### 15.7. Validacion Operativa
Se agrego:
- workflow CI en [backend-validation.yml](/c:/Users/Alamb/Documents/Vexxo_Backend_API/.github/workflows/backend-validation.yml)

Que valida:
- compilacion de codigo Python
- `manage.py check` con SQLite local en CI

Pendiente en entorno real:
- aplicar migraciones nuevas
- probar callback OAuth con credenciales reales
- probar refresh rotation y reuse detection contra tu cliente frontend

## 16. Correcciones De Coherencia Y Estado Final

### 16.1. Outbox Persistente De `identity` Corregido
Archivos:
- [identity/eventing/models.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/models.py)
- [identity/eventing/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/services.py)
- [identity/users/services/event_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/event_service.py)

Correccion aplicada:
- `publish_user_event_after_commit()` ya no llama una firma incompatible
- `publish_identity_after_commit()` ahora recibe `event_type`, `aggregate_type`, `aggregate_id`, `payload`, `metadata`, `priority`, `correlation_id` y `causation_id`
- el outbox persiste tambien `priority`, `correlation_id` y `causation_id`
- para eventos anonimos o pre-user ya no se tolera `aggregate_id` vacio: se resuelve un aggregate id estable a partir de `user_id`, `entity_id`, `correlation_id`, `state` o un hash estable del payload

Politica actual de agregados:
- eventos ligados a usuario: `aggregate_type=identity_user`
- eventos ligados a entidad interna: `aggregate_type=identity_<entity_type>`
- flujos previos a usuario materializado, como social auth: `aggregate_type=identity_flow`

Que significa en lenguaje simple:
- antes existia riesgo real de romper la publicacion de eventos de `users`, `devices`, `sessions`, `consents` y `permissions`
- ahora `identity` vuelve a tener el mismo patron serio que `accounts`: persistir primero, publicar despues

Flujo real:
1. una vista o servicio de identidad construye el payload
2. `publish_user_event_after_commit()` delega en `identity.eventing`
3. se crea `IdentityDomainEventOutbox`
4. al commit se publica al bus local
5. si el dispatcher global esta activo, luego el evento puede salir hacia Pub/Sub

Ejemplo tecnico:
```python
publish_user_event_after_commit(
    event_type=UserDomainEventTypes.USER_PERMISSION_GRANTED,
    payload={"user_id": "123", "entity_type": "permission_grant"},
    metadata={"source": "identity.permissions.grant_permission"},
    priority=EventPriority.NORMAL,
    correlation_id="corr-abc",
)
```

### 16.2. OAuth Social Con Handoff Seguro
Archivos:
- [identity/users/views/auth.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views/auth.py)
- [identity/users/services/oauth_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/oauth_service.py)
- [identity/social_identities/models.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/social_identities/models.py)
- [identity/users/urls.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/urls.py)

Decision de seguridad:
- `GET /auth/social/{provider}/callback/` ya no crea sesion ni emite tokens
- el callback valida `state`, intercambia `code`, recupera el perfil, resuelve linking o login y devuelve un `handoff_code` temporal
- la sesion y los JWT solo se crean con `POST /auth/social/exchange/`
- el `handoff_code` ahora se consume de forma atomica dentro de transaccion
- el mismo handoff no debe poder emitir dos sesiones concurrentes

Endpoints:
- `GET /api/identity/users/auth/social/providers/`
- `GET /api/identity/users/auth/social/{provider}/start/`
- `GET /api/identity/users/auth/social/{provider}/callback/`
- `POST /api/identity/users/auth/social/exchange/`
- `GET /api/identity/users/auth/social/identities/`
- `DELETE /api/identity/users/auth/social/{provider}/unlink/`

Flujo real:
1. frontend llama `GET /auth/social/google/start/`
2. backend entrega `authorization_url` y `state`
3. proveedor redirige a `GET /auth/social/google/callback/code=...&state=...`
4. backend valida el callback y responde `handoff_code`
5. frontend llama `POST /auth/social/exchange/` con ese `handoff_code`
6. backend crea `UserSession`, registra `Device` y devuelve `access` + `refresh`

Ejemplo del callback:
```json
{
  "detail": "Proveedor validado. Intercambia el handoff por una sesion via POST.",
  "provider": "google",
  "handoff_code": "....",
  "handoff_expires_at": "2026-03-27T12:00:00Z"
}
```

Ejemplo del exchange:
```json
{
  "handoff_code": "....",
  "device_type": "web",
  "platform": "chrome",
  "device_fingerprint": "browser-xyz"
}
```

Respuesta del exchange:
```json
{
  "detail": "Sesion social creada.",
  "provider": "google",
  "tokens": {
    "refresh": "...",
    "access": "..."
  },
  "session": {
    "session_id": 10,
    "family_id": "....",
    "risk_level": "low",
    "requires_step_up": false
  }
}
```

Protecciones adicionales:
- respuestas del callback y del exchange salen con `Cache-Control: no-store`
- no hay auto-merge agresivo por email salvo `IDENTITY_SOCIAL_AUTO_LINK_BY_EMAIL=True`
- el handoff se invalida por uso unico real y por expiracion

### 16.3. Permisos: Coexistencia Real Entre Grant Manual Y Entitlement
Archivos:
- [identity/permissions/models/permission_grant.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/models/permission_grant.py)
- [identity/permissions/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/services.py)

Correccion aplicada:
- la unicidad ya no es solo `user + permission_code + scope`
- ahora tambien incluye `source` y `grant_kind`
- `grant_permission()` usa esa misma llave al crear o actualizar

Resultado:
- un entitlement derivado del plan puede coexistir con un override manual
- un grant derivado de consentimiento no pisa un grant administrativo
- la lectura efectiva de permisos ya devuelve codigos deduplicados

Ejemplo conceptual:
- `accounts.multi_primary.enabled` por plan `plus`
- `accounts.multi_primary.enabled` como override manual para soporte

Antes:
- uno podia sobreescribir al otro

Ahora:
- ambos pueden coexistir y quedan trazados por `source` y `grant_kind`

### 16.4. Proyecciones Solo Async En Produccion
Archivos:
- [finance/accounts/services/intelligence_dispatch_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/intelligence_dispatch_service.py)
- [finance/accounts/views/intelligence_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/views/intelligence_views.py)
- [identity/users/views/dashboard.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views/dashboard.py)
- [finance/accounts/services/user_integration_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/user_integration_service.py)

Decision aplicada:
- en produccion o cloud, las proyecciones de inteligencia no deben recalcularse en el path del request
- el sistema intenta primero agendar `Cloud Tasks`
- solo hace fallback local cuando el entorno lo permite explicitamente

Variables relevantes:
- `ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_ENABLED`
- `ACCOUNTS_INTELLIGENCE_HANDLER_URL`
- `ACCOUNTS_INTELLIGENCE_LOCAL_FALLBACK_ENABLED`

Comportamiento esperado:
- `POST /api/finance/accounts/.../refresh/` puede responder `202 Accepted`
- el dashboard del usuario puede devolver snapshots existentes con bandera `projection_pending`
- los servicios de lifecycle ya no fuerzan recomputacion pesada dentro del request normal
- ahora las respuestas tambien pueden incluir `projection_status` con:
  - si la proyeccion sigue pendiente
  - si Cloud Tasks esta lista
  - si el fallback local esta permitido
  - timestamp y edad del ultimo snapshot materializado

Esto sirve para:
- observabilidad funcional en frontend y soporte
- detectar usuarios atascados sin snapshot
- separar claramente "dato parcial" de "dato sano y fresco"

### 16.5. Consentimientos Desacoplados Del Stub Local
Archivos:
- [identity/consents/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/services.py)
- [identity/consents/event_handlers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/consents/event_handlers.py)
- [integrations_stub/banks/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/integrations_stub/banks/views.py)

Correccion aplicada:
- `identity.consents` ya no llama directamente al stub como dependencia primaria
- ahora existe `dispatch_consent_revocation_teardown(...)`
- primero intenta enviar el teardown a un endpoint interno configurable
- solo usa fallback local si la configuracion lo permite

Separacion de secretos:
- `ACCOUNTS_SYNC_INTERNAL_TOKEN` sigue protegiendo sync de cuentas
- `IDENTITY_CONSENTS_INTERNAL_TOKEN` protege teardown de consentimientos

Variables nuevas:
- `IDENTITY_CONSENT_TEARDOWN_HANDLER_URL`
- `IDENTITY_CONSENTS_INTERNAL_TOKEN`
- `IDENTITY_CONSENT_LOCAL_FALLBACK_ENABLED`

Ejemplo de payload interno:
```json
{
  "user_id": "123",
  "provider": "bancolombia",
  "consent_type": "open_banking_data",
  "event": {
    "type": "users.consent.revoked.v1",
    "correlation_id": "corr-123"
  }
}
```

### 16.6. Migraciones Nuevas De Este Ajuste
- [identity/eventing/migrations/0002_outbox_transport_fields.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/migrations/0002_outbox_transport_fields.py)
- [identity/social_identities/migrations/0002_social_auth_handoff.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/social_identities/migrations/0002_social_auth_handoff.py)
- [identity/permissions/migrations/0003_permission_scope_source_kind_constraint.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/migrations/0003_permission_scope_source_kind_constraint.py)

### 16.7. Validacion Hecha
Validado en este entorno:
- compilacion sintactica con `py_compile` de los archivos ajustados
- limpieza dirigida del `mojibake` en la documentacion principal y la documentacion de `identity`

No validado aqui:
- `manage.py check`
- migraciones aplicadas
- callback OAuth contra proveedores reales

Motivo:
- el interprete disponible en este shell no tiene Django instalado ni el virtualenv activo del proyecto

## 17. Ajuste Final: SPA Callback, Outbox Operable Y Permisos Con Precedencia

### 17.1. Social Auth Ahora Es SPA/Mobile-First
Decision de arquitectura aplicada:
- el proveedor social debe redirigir al frontend/app
- el frontend recibe `code` y `state`
- el frontend llama `POST /api/identity/users/auth/social/exchange/`
- el backend hace el exchange real, crea o vincula usuario, registra dispositivo/sesion y emite eventos

Archivos:
- [identity/users/services/oauth_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/services/oauth_service.py)
- [identity/users/views/auth.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views/auth.py)
- [backend/settings.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/backend/settings.py)
- [.env](/c:/Users/Alamb/Documents/Vexxo_Backend_API/.env)

Cambio de contrato:
- `GET /auth/social/{provider}/start/` ahora puede construir la URL con `redirect_uri` de frontend
- `POST /auth/social/exchange/` acepta:
  - camino moderno: `provider`, `code`, `state`, `redirect_uri`
  - camino legacy/compatibilidad: `handoff_code`
- `GET /auth/social/{provider}/callback/` queda como compatibilidad backend-callback, no como camino principal

Variables nuevas:
- `GOOGLE_OAUTH_FRONTEND_CALLBACK_URL`
- `FACEBOOK_OAUTH_FRONTEND_CALLBACK_URL`

### 17.2. Outbox De Identity Ya Tiene Superficie Operativa
Archivos:
- [identity/eventing/views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/views.py)
- [identity/eventing/serializers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/serializers.py)
- [identity/eventing/urls.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/eventing/urls.py)
- [api/v1/routers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/api/v1/routers.py)

Endpoints nuevos:
- `GET /api/identity/eventing/outbox-identidad/`
- `GET /api/identity/eventing/outbox-identidad/{id}/`
- `POST /api/identity/eventing/outbox-identidad/{id}/publish_now/`
- `POST /api/identity/eventing/outbox-identidad/{id}/retry/`
- `POST /api/identity/eventing/outbox-identidad/{id}/release_lock/`
- `GET /api/identity/eventing/outbox-identidad/health/`
- `GET /api/identity/eventing/outbox-identidad/contracts/`

Resultado:
- `identity` ya no solo persiste eventos; ahora tambien tiene una API operativa comparable a `accounts`

### 17.3. Secretos Internos Separados De Verdad
Decision aplicada:
- `ACCOUNTS_INTELLIGENCE_INTERNAL_TOKEN` ya no hereda por defecto de `ACCOUNTS_SYNC_INTERNAL_TOKEN`
- `IDENTITY_CONSENTS_INTERNAL_TOKEN` ya no hereda por defecto de `ACCOUNTS_SYNC_INTERNAL_TOKEN`

Esto obliga a una configuracion mas explicita, pero reduce blast radius entre:
- sync de cuentas
- refresh de inteligencia
- teardown de consentimientos

### 17.4. Permisos Efectivos Con Precedencia
Archivos:
- [identity/permissions/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/services.py)
- [identity/permissions/views/permission_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/views/permission_views.py)

Cambio aplicado:
- ya no solo se deduplican codigos
- ahora se calcula una resolucion efectiva por `permission_code`
- la precedencia actual es:
  - `override`
  - `manual`
  - `entitlement`

El endpoint `effective` ahora puede exponer:
- `permission_codes`
- `resolution`

Eso permite ver de donde sale cada capacidad efectiva y cual grant esta dominando.

### 17.5. Catalogo De Eventos Mas Honesto
Archivos:
- [finance/accounts/domain/events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/domain/events.py)
- [identity/users/domain/events.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/domain/events.py)

Cambio aplicado:
- `accounts` ahora expone `pattern_local_listeners` y `effective_local_listeners`
- `identity` ya no declara falsamente listeners patron `users.*` si no existen

Resultado:
- el contrato de eventos refleja mejor lo que realmente escucha el sistema

## 18. Deny Explicito Y Salud Operativa De Proyecciones

### 18.1. Permisos Con `denied` Explicito
Archivos:
- [identity/permissions/models/permission_grant.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/models/permission_grant.py)
- [identity/permissions/services.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/services.py)
- [identity/permissions/views/permission_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/views/permission_views.py)
- [identity/permissions/serializers/permission_serializers.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/permissions/serializers/permission_serializers.py)

Cambio aplicado:
- `PermissionStatus` ahora incluye `denied`
- `deny` ya no se modela como "absence of grant" ni como revocacion ambigua
- existe precedencia efectiva entre:
  - `override`
  - `manual`
  - `entitlement`
- dentro de la misma prioridad, `denied` domina sobre `granted`

Ejemplo tecnico:
```text
plan => reports.extended.enabled = granted
support override => reports.extended.enabled = denied
resultado efectivo => reports.extended.enabled = disabled
```

Endpoints relevantes:
- `POST /api/identity/permissions/grants/`
  Puede crear un grant con `status=denied` si el `grant_kind` es `override` o `manual`.
- `POST /api/identity/permissions/grants/{id}/deny/`
  Marca un grant existente como denegado explicito.
- `GET /api/identity/permissions/grants/effective/`
  Ahora devuelve:
  - `permission_codes`
  - `resolution`

Evento nuevo:
- `users.permission.denied.v1`

Que significa:
- ya no solo sabes que un permiso existe o fue revocado
- ahora tambien sabes que fue denegado explicitamente por una capa superior

### 18.2. Salud Operativa De Proyecciones Async
Archivos:
- [finance/accounts/services/intelligence_health_service.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/services/intelligence_health_service.py)
- [finance/accounts/views/intelligence_views.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/finance/accounts/views/intelligence_views.py)
- [identity/users/views/dashboard.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/identity/users/views/dashboard.py)
- [backend/settings.py](/c:/Users/Alamb/Documents/Vexxo_Backend_API/backend/settings.py)
- [.env](/c:/Users/Alamb/Documents/Vexxo_Backend_API/.env)

Que agrega:
- lectura de `projection_health`
- deteccion de:
  - `pending`
  - `pending_too_long`
  - `stale`
  - `pipeline_unavailable`
- thresholds configurables
- alertas operativas deduplicadas para que el problema no quede solo en logs

Campos nuevos en la respuesta:
- `health_level`
- `pending_too_long`
- `stale`
- `pipeline_unavailable`
- `effective_age_seconds`
- `active_alert_codes`

Endpoints donde ahora aparece:
- `GET /api/identity/users/dashboard/`
- `GET /api/finance/accounts/snapshots-portafolio-cuenta/overview/`
- `GET /api/finance/accounts/snapshots-portafolio-cuenta/health/`
- `POST /api/finance/accounts/snapshots-portafolio-cuenta/refresh/`

Variables nuevas:
- `ACCOUNTS_INTELLIGENCE_ALERTS_ENABLED`
- `ACCOUNTS_INTELLIGENCE_MAX_PENDING_SECONDS`
- `ACCOUNTS_INTELLIGENCE_STALE_AFTER_SECONDS`

Ejemplo simple:
```json
{
  "projection_health": {
    "health_level": "warning",
    "pending": true,
    "pending_too_long": true,
    "stale": false,
    "pipeline_unavailable": false,
    "effective_age_seconds": 1432,
    "active_alert_codes": ["pending_too_long"]
  }
}
```

En lenguaje simple:
- si la inteligencia de cuentas se demora demasiado
- o deja de materializarse
- el sistema ya no solo devuelve `projection_status`
- tambien expresa salud operativa y puede dejar una alerta persistente
