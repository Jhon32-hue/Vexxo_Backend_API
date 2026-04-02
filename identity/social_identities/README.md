# identity.social_identities

## Que hace

`identity.social_identities` modela identidades sociales externas vinculadas a
un usuario interno de Vexxo.

Hoy el modulo si tiene dominio real en modelos:

- `UserSocialIdentity`
- `SocialAuthHandoff`

## Rol En El Producto

Su trabajo es separar dos cosas:

- la identidad interna canonica del usuario de Vexxo
- la relacion con proveedores sociales como Google o Facebook

Eso permite:

- login social
- vinculacion de una identidad externa a un usuario existente
- trazabilidad de ultimo login social
- handoff corto para terminar un flujo de autenticacion o linking

## Modelos Principales

### `UserSocialIdentity`

Representa una identidad externa vinculada.

Campos clave observados:

- `user`
- `provider`
- `provider_user_id`
- `email`
- `email_verified`
- `full_name`
- `avatar_url`
- `is_active`
- `linked_at`
- `last_login_at`
- `unlinked_at`
- `metadata`

Reglas visibles:

- unicidad por `provider + provider_user_id`
- puede marcarse `unlink`
- puede actualizar `last_login_at` con `touch_login`

### `SocialAuthHandoff`

Representa un codigo de handoff temporal para cerrar un flujo de auth social.

Campos clave:

- `code`
- `provider`
- `user`
- `identity`
- `login_mode`
- `created_user`
- `linked_identity`
- `expires_at`
- `used_at`
- `metadata`

Reglas visibles:

- `mark_used()`
- propiedad `is_valid`

## Casos De Uso

### Vincular una cuenta social

1. el usuario autentica con un proveedor externo
2. se crea o reutiliza `UserSocialIdentity`
3. la identidad queda asociada al usuario interno
4. el sistema puede registrar metadata y ultimo login

### Completar un handoff de login

1. un flujo de autenticacion social genera un codigo temporal
2. se persiste `SocialAuthHandoff`
3. el cliente consume ese handoff antes de expiracion
4. el sistema marca el codigo como usado

## Relacion Con Otros Modulos

- `identity.users`
  la identidad social siempre se cuelga de un usuario interno.
- `identity.sessions`
  un login social exitoso puede terminar en una sesion nueva o actualizada.
- `identity.devices`
  un nuevo login social puede asociarse a un dispositivo nuevo o sospechoso.
- `identity.permissions` y `identity.consents`
  no controlan el login social, pero si todo lo que el usuario puede hacer
  despues de autenticarse.

## Encaje Con GCP

En una topologia cloud-first este modulo suele vivir detras de:

- API Gateway
- Cloud Run BFF
- Identity Platform o un proveedor equivalente

La identidad social externa no reemplaza la identidad de Vexxo; solo la
enriquece y ayuda en autenticacion o linking.

## Estado Actual

Hoy el modulo tiene modelos y migraciones reales, pero no detecte en esta
pasada una superficie REST o servicios de aplicacion equivalentes a otros
modulos core. Eso sugiere que el dominio ya esta modelado, pero el flujo
publico de auth social se resuelve desde otra capa o aun no esta completamente
abierto.
