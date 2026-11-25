# identity.users

## Modelos canonicos en helpers de capacidad

Los imports son locales al metodo para respetar la inicializacion de Django.
`can_add_contact` usa `contacts.models.Contact`; `can_generate_monthly_report`
usa `reports.monthly_reports.models.MonthlyReportClose` y cuenta creaciones del
mes solicitado. No convierte errores de importacion en permisos concedidos.
`can_add_api_connection` conserva el contrato de limite por cuentas conectadas:
cuentas activas/congeladas con provider y external_id, no cantidad de conexiones
de un proveedor. No depende del antiguo stub `FinancialConnection`.

Regresion sin DB: `python manage.py test identity.users.test_import_contracts`.

## Que hace

Este modulo concentra identidad base de usuario, plan efectivo de producto y
capabilities visibles para mobile/web.

No ejecuta integraciones largas ni rails externos. Su responsabilidad es:

- definir `User` y el plan efectivo del usuario
- exponer `plan_matrix` y overrides comerciales
- publicar eventos `users.*`
- entregar a la app capacidades, permisos derivados y usage operativo

## Rol En El Producto

De cara al usuario, este modulo responde:

- quien soy en Vexxo
- que plan tengo
- que funciones deberia ver desbloqueadas
- cuanto uso llevo frente a mis limites
- que mensajes de upgrade o bloqueo son validos

## Vista visual

```mermaid
classDiagram
    class User {
        +email
        +plan
        +status
        +preferred_currency
        +timezone_name
        +locale
        +onboarding_completed
        +last_seen
    }

    class UserPermissionGrant {
        +permission_code
        +status
        +source
        +grant_kind
    }

    class UserConsent {
        +consent_type
        +provider
        +scope_code
        +status
    }

    class UserProductUsageProjection {
        +active_accounts_count
        +payments_count_month
        +payments_volume_month
        +ai_used_month
        +shared_memberships_count
    }

    class UserOnboardingProfile {
        +registration_country
        +age_range
        +preferred_currencies
        +income_sources
        +employment_type
        +finance_method
        +monthly_income_range
        +use_cases
        +questionnaire_version
        +profile_version
        +completed_at
    }

    User "1" --> "0..1" UserOnboardingProfile : completes
    User "1" --> "*" UserPermissionGrant : derives_capabilities
    User "1" --> "*" UserConsent : authorizes
    User "1" --> "1" UserProductUsageProjection : summarized_into
```

## Secuencia critica: register

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as Django BFF
    participant U as identity.users
    participant SQL as Cloud SQL
    participant IO as Identity Outbox
    participant PERM as identity.permissions
    participant PROJ as identity.eventing

    FE->>API: register
    API->>U: validate + create user
    U->>SQL: insert users_user
    U->>IO: enqueue users.registered.v1
    API-->>FE: 201 user
    IO->>PERM: sync plan permissions
    IO->>PROJ: bootstrap usage projection
```

## Flujos principales

### Onboarding post-registro

`POST /api/identity/users/onboarding/complete/` ya no activa solamente una
bandera. El request se valida contra catalogos cerrados y se persiste en
`UserOnboardingProfile` dentro de la misma transaccion que actualiza moneda,
locale, zona horaria y `User.onboarding_completed`.

Propiedades operativas:

- `User` se bloquea con `SELECT ... FOR UPDATE` para serializar finalizaciones
  concurrentes.
- `profile_version` permite enviar `base_version`; una version obsoleta recibe
  `409 onboarding_version_conflict` con el perfil autoritativo.
- un retry con el mismo payload no incrementa la version ni duplica
  `users.onboarding.completed.v1`.
- ingresos, edad y fuentes son datos `confidential`; no se copian al outbox,
  logs ni notificaciones.
- la respuesta contiene el `UserMeSerializer` completo, incluido
  `onboarding_profile`, y es la confirmacion que Flutter debe aceptar como
  verdad del servidor.
- el bootstrap de categorias/equipo permanece asociado a `users.registered.v1`;
  onboarding no crea un segundo flujo de bootstrap financiero.

```mermaid
sequenceDiagram
    participant FE as Flutter
    participant API as CompleteOnboardingView
    participant SVC as onboarding_service
    participant DB as PostgreSQL
    participant OB as Identity Outbox

    FE->>API: payload validado + base_version opcional
    API->>SVC: complete_onboarding
    SVC->>DB: lock User + upsert profile + update User
    DB->>OB: users.onboarding.completed.v1 al primer cierre
    API-->>FE: perfil autoritativo + profile_version
```

### Auth y comunicaciones del usuario

`identity.users` ya cubre estos caminos:

- registro `email + password`
- login con `email` o `username` interno, JWT y sesion/dispositivo
- Flutter registra y luego inicia sesion automaticamente con el mismo correo;
  un correo existente responde `409 email_exists`, nunca un error `500`
- `Idempotency-Key` se conserva durante el intento movil. Repetir la misma
  operacion devuelve la cuenta creada con `X-Idempotent-Replay: true`; reutilizar
  la clave para otro correo devuelve `409 idempotency_conflict`
- refresh seguro con deteccion de reuse
- logout con revocacion
- OAuth2 Google y Facebook
- recuperacion de contrasena por correo como fallback
- recuperacion mobile-first por codigo temporal de 2 minutos
- step-up por codigo temporal en dispositivos `unknown` o `suspicious`
- configuracion de contrasena para usuarios autenticados
- correo de bienvenida desacoplado del request path
- preferencia de newsletter y correos lifecycle via `notifications.preferences`
- validacion de contrasena con longitud minima, mayuscula, minuscula y numero

### Secuencia critica: reset de contrasena

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as identity.users
    participant SQL as Cloud SQL
    participant PREF as notifications.preferences
    participant MAIL as communication_service
    participant ND as NotificationDelivery

    FE->>API: POST /auth/password-reset/request
    API->>SQL: lookup user by email
    API->>MAIL: build uid + token
    MAIL->>PREF: resolve preferences
    MAIL->>ND: create channel=email delivery
    MAIL-->>FE: 200 generic response
```

### Secuencia critica: recovery code mobile

```mermaid
sequenceDiagram
    participant FE as Mobile
    participant API as identity.users
    participant SQL as Cloud SQL
    participant CH as UserAuthChallenge
    participant DEL as NotificationDelivery
    participant SMS as SMS provider / local stub

    FE->>API: POST /auth/password-recovery/request-code
    API->>SQL: resolve active user by phone
    API->>CH: create password_recovery challenge
    API->>DEL: persist sms_stub delivery
    API->>SMS: dispatch code or stub local
    API-->>FE: 200 generic
    FE->>API: POST /auth/password-recovery/confirm-code
    API->>CH: validate code + ttl + attempts
    API->>SQL: set new password + revoke sessions
    API-->>FE: 200 success
```

### Secuencia critica: step-up embebido

```mermaid
sequenceDiagram
    participant FE as Mobile / Web
    participant API as identity.users
    participant SES as identity.sessions
    participant CH as UserAuthChallenge
    participant MSG as integrations_stub.messaging

    FE->>API: login/social exchange
    API->>SES: create session
    SES-->>API: requires_step_up=true
    API->>CH: issue step_up challenge
    API->>MSG: dispatch code
    API-->>FE: tokens + session + step_up
    FE->>API: POST /auth/step-up/confirm-code
    API->>CH: validate one-time code
    API->>SES: clear requires_step_up + revoke risky siblings
    API-->>FE: step-up completed
```

### Secuencia critica: social login

```mermaid
sequenceDiagram
    participant FE as Frontend / Mobile
    participant API as identity.users
    participant OAUTH as Google/Facebook
    participant DEV as identity.devices
    participant SES as identity.sessions

    FE->>API: GET /auth/social/{provider}/start
    API-->>FE: authorization_url + state
    FE->>OAUTH: redirect user
    OAUTH-->>FE: code + state
    FE->>API: POST /auth/social/exchange
    API->>DEV: register_or_update_device
    API->>SES: register_user_session
    API-->>FE: access + refresh + session
```

### Plan y capabilities

1. `User.plan` es la fuente comercial canónica.
2. `identity.users.domain.plan_matrix` traduce ese plan a capabilities.
3. `identity.permissions` deriva permission codes booleanos.
4. Los bounded contexts aplican guards propios usando esas capabilities.

### Usage projection

`identity.users.services.product_usage_projection_service` materializa una
proyeccion de uso por usuario.

Objetivo:

- evitar `count()` y `aggregate()` repetidos contra OLTP en cada request
- servir a mobile un snapshot compacto de uso y limites
- preparar el camino para proyectores incrementales y pipelines cloud

Estado actual:

- la lectura del API ya usa la proyeccion
- la proyeccion se refresca desde eventos de `accounts.*`, `alerts.*`,
  `payments.*` y productores locales como reglas y pagos programados
- si la proyeccion aun no existe, se reconstruye una vez para bootstrap

### Estrategia de actualizacion

La proyeccion funciona en modo hibrido con direccion incremental:

- delta exacto:
  - `rules_count`
  - `manual_accounts_count`
  - `connected_accounts_count`
  - `active_accounts_count`
  - `shared_memberships_count`
  - `ai_used_month`
  - `payments_count_month`
  - `payments_volume_month`
  - `payments_count_day`
  - `payments_volume_day`
  - `payouts_count_month`
  - `payouts_volume_month`
  - `payouts_count_day`
  - `payouts_volume_day`
- resync por slice:
  - `scheduled_payments_active_count`
  - fallback mensual cuando cambia el periodo
- rebuild completo:
  - fallback cuando no hay proyeccion o falta contexto suficiente

Para los eventos del bus se guarda un checkpoint persistente por
`owner + event_key`. Eso evita aplicar dos veces el mismo delta si el worker o
el bus reintentan una entrega.

## Limites diarios y caps operativos

`identity.users.services.product_access_service` ahora distingue:

- limites comerciales por plan
- caps operativos internos de Vexxo por proveedor/rail

Ejemplo:

- el plan puede permitir pagar mas
- pero Vexxo puede bloquear igual por `platform_daily_payment_cap`
  si ese rail o proveedor ya llego al volumen operativo seguro del dia

Hoy esos caps operativos son configurables por `settings` y pueden no existir
por defecto. La idea es no acoplar el producto a un PSP unico ni a limites
hardcodeados de un proveedor puntual.

Eso evita confundir capacidad de infraestructura con capacidad operativa real.

## Relacion con otros modulos

- `identity.eventing`: persiste eventos y read models
- `identity.permissions`: deriva entitlements desde el plan
- `finance.accounts`: emite eventos para cuentas y sharing
- `alerts.alerts`: emite eventos de enriquecimiento IA
- `payments.payment_intents`: emite eventos de pagos externos
- `payments.scheduled_payments`: representa planificacion futura

## Encaje Con GCP

`identity.users` funciona bien como capa ligera en Cloud Run:

- el BFF responde auth, perfil, dashboard y capabilities
- el uso no se recalcula contra OLTP en cada request; se lee desde proyeccion
- los eventos `users.*` se persisten y publican por outbox
- futuros servicios de growth, billing o analytics pueden consumir esos eventos

Esto evita convertir al API Gateway o al BFF en un coordinador pesado.

## Esqueleto/futuro

Todavia faltan productores canonicos por evento para:

- `documents` / OCR

Cuando esos modulos maduren, deben proyectar `UserProductUsageProjection`
sin volver a meter lecturas OLTP pesadas en el request path.

## Endpoints clave de auth

- `POST /api/identity/users/auth/register/`
- `POST /api/identity/users/auth/login/`
- `POST /api/identity/users/auth/refresh/`
- `POST /api/identity/users/auth/logout/`
- `POST /api/identity/users/auth/password-reset/request/`
- `POST /api/identity/users/auth/password-reset/confirm/`
- `POST /api/identity/users/auth/password-recovery/request-code/`
- `POST /api/identity/users/auth/password-recovery/confirm-code/`
- `POST /api/identity/users/auth/step-up/request-code/`
- `POST /api/identity/users/auth/step-up/confirm-code/`
- `POST /api/identity/users/auth/set-password/`
- `GET /api/identity/users/auth/social/providers/`
- `GET /api/identity/users/auth/social/{provider}/start/`
- `GET /api/identity/users/auth/social/{provider}/callback/`
- `POST /api/identity/users/auth/social/exchange/`
- `GET /api/identity/users/me/`
- `POST /api/identity/users/onboarding/complete/`

## Relacion con notificaciones y correo

## Seguridad operativa

- Login y recovery consumen buckets durables en PostgreSQL; no dependen de la
  memoria de un proceso Gunicorn.
- El reset por correo acepta solo hosts de
  `IDENTITY_PASSWORD_RESET_ALLOWED_HOSTS`; un redirect no permitido cae al URL
  configurado por backend sin revelar si el usuario existe.
- JWT usa `JWT_SIGNING_KEY`, separada de `DJANGO_SECRET_KEY` cuando se configura.
- Un access token emitido por login queda ligado al JTI de `UserSession`; rotar
  refresh, revocar dispositivo, cambiar password o cerrar la familia invalida
  el token anterior aunque su `exp` no haya vencido.
- Recovery usa `IDENTITY_RECOVERY_HASH_KEY` y conserva codigo, expiracion,
  intentos, supersession y respuesta anti-enumeracion.
- PIN y biometria son controles locales de Flutter, no factores enviados al
  backend.

## Relacion con notificaciones y correo

- el correo de bienvenida se dispara desde `users.registered.v1`, no desde el request de registro
- un fallo de entrega del correo de bienvenida queda trazado en notificaciones y
  no revierte ni invalida la cuenta ya creada
- el request de recovery responde siempre 200 para no filtrar si el correo o telefono existen
- el registro no exige email verification para activar la cuenta; el email de bienvenida permanece informativo
- el canal principal embebido para recovery y step-up es codigo corto temporal al telefono
- el PIN de 4 digitos o biometria pertenece al dispositivo/mobile app, no al backend como secreto principal
- `notifications.preferences` decide si se permiten correos lifecycle
- `NotificationDelivery(channel=email)` guarda trazabilidad de welcome y password reset
- `integrations_stub.messaging` abstrae el transporte SMS/WhatsApp fuera de `identity.users`

## Local vs cloud

- local/dev:
  - recovery y step-up usan `integrations_stub.messaging` con `IDENTITY_MESSAGE_BACKEND=local_stub`
  - si `IDENTITY_RECOVERY_DEBUG_REVEAL_CODE=True`, el codigo aparece solo en `NotificationDelivery.payload.debug_code`
- cloud/prod:
  - el backend ya persiste `UserAuthChallenge`
  - el adapter real de SMS/WhatsApp debe vivir fuera de `identity.users`
  - el contrato del flujo no cambia: request generico, confirm con codigo corto

## Nota de limites de alcance

- `UserAuthChallenge` ya reserva `magic_link` como purpose
- no se cableo aun a invitaciones de `finance.accounts` o `social.teams`
- esa integracion debe hacerse desde el bounded context dueno de la invitacion,
  no desde auth puro, para no mezclar sharing con login

## MFA

`/api/identity/users/auth/mfa/` ofrece estado, enrolamiento/confirmacion TOTP,
step-up y desactivacion. La semilla solo se muestra al enrolar; los codigos de
recuperacion se muestran una vez y cada uno se consume una sola vez.

Cuando MFA esta activo, recovery exige ademas TOTP o un recovery code. Cambio
de password, reset completado, revocacion de dispositivo, suspension y riesgo
critico invalidan inmediatamente las familias de sesion correspondientes. La
politica por operacion esta centralizada en `security_policy.py` y documentada
en [Garantias de identidad](../../docs/IDENTITY_SECURITY_ASSURANCE.md).

<!-- backend-source-audit:start -->
## Evidencia del codigo y mapa de dependencias

Inventario estatico reproducible del checkout. Describe declaraciones e imports;
no prueba despliegue, permisos efectivos ni que todos los caminos se ejecuten.
Las rutas son locales a su URLConf: el prefijo publico se consulta en
[`api/v1/routers.py`](../../api/v1/routers.py).

- Archivos Python de implementacion: **35** (excluye tests y migraciones).
- Huella SHA-256 del codigo inventariado: `9b2636e45a637d9675f52c910a5ae101bea809f36c432d7b0330dd71402ddd5c`.
- Familias detectadas: models, serializers, services, views.

### Declaraciones de modelos detectadas

- `UserAuthChallenge` en [identity/users/models/auth_challenge.py](models/auth_challenge.py).
- `UserMfaMethod` en [identity/users/models/mfa.py](models/mfa.py).
- `UserOnboardingProfile` en [identity/users/models/onboarding.py](models/onboarding.py).

### Rutas declaradas

| Patron local | Fuente |
| --- | --- |
| `` | [identity/users/urls.py](urls.py) |
| `admin/users/ [DRF router]` | [identity/users/urls.py](urls.py) |
| `auth/login/` | [identity/users/urls.py](urls.py) |
| `auth/logout/` | [identity/users/urls.py](urls.py) |
| `auth/mfa/disable/` | [identity/users/urls.py](urls.py) |
| `auth/mfa/status/` | [identity/users/urls.py](urls.py) |
| `auth/mfa/totp/confirm/` | [identity/users/urls.py](urls.py) |
| `auth/mfa/totp/enroll/` | [identity/users/urls.py](urls.py) |
| `auth/mfa/verify/` | [identity/users/urls.py](urls.py) |
| `auth/password-recovery/confirm-code/` | [identity/users/urls.py](urls.py) |
| `auth/password-recovery/request-code/` | [identity/users/urls.py](urls.py) |
| `auth/password-reset/confirm/` | [identity/users/urls.py](urls.py) |
| `auth/password-reset/request/` | [identity/users/urls.py](urls.py) |
| `auth/refresh/` | [identity/users/urls.py](urls.py) |
| `auth/register/` | [identity/users/urls.py](urls.py) |
| `auth/set-password/` | [identity/users/urls.py](urls.py) |
| `auth/social/<str:provider>/callback/` | [identity/users/urls.py](urls.py) |
| `auth/social/<str:provider>/start/` | [identity/users/urls.py](urls.py) |
| `auth/social/<str:provider>/unlink/` | [identity/users/urls.py](urls.py) |
| `auth/social/exchange/` | [identity/users/urls.py](urls.py) |
| `auth/social/identities/` | [identity/users/urls.py](urls.py) |
| `auth/social/providers/` | [identity/users/urls.py](urls.py) |
| `auth/step-up/confirm-code/` | [identity/users/urls.py](urls.py) |
| `auth/step-up/request-code/` | [identity/users/urls.py](urls.py) |
| `dashboard/` | [identity/users/urls.py](urls.py) |
| `event-contract/` | [identity/users/urls.py](urls.py) |
| `me/` | [identity/users/urls.py](urls.py) |
| `onboarding/complete/` | [identity/users/urls.py](urls.py) |

### Diagrama de dependencia estatica

Las flechas representan imports entre paquetes, no eventos ni orden de ejecucion.

```mermaid
flowchart LR
    M["identity.users"]
    M --> D0["alerts"]
    M --> D1["common"]
    M --> D2["contacts"]
    M --> D3["finance"]
    M --> D4["integrations"]
    M --> D5["integrations_stub"]
    M --> D6["notifications"]
    M --> D7["payments"]
    M --> D8["planning"]
    M --> D9["reports"]
    M --> D10["security"]
    M --> D11["social"]
```

Flujos transversales: [flujo actualizado](../../docs/BACKEND_CURRENT_FLOW.md).

Regeneracion: `py -3 scripts/audit_backend_docs.py --write`.
Comprobacion de deriva: `py -3 scripts/audit_backend_docs.py --check`.
<!-- backend-source-audit:end -->
