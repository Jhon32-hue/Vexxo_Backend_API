"""
Servicios OAuth2/OIDC para autenticacion social.

Descripcion general:
- resuelve configuracion, URLs de autorizacion, callbacks y linking de
  identidades sociales de Google y Facebook
- deja el flujo listo para funcionar en local, Cloud Run o delante de Identity
  Platform de GCP

Analisis detallado:
- esta capa ya no solo prepara URLs; ahora valida `state`, intercambia `code`
  por tokens, consulta perfil remoto y decide si debe hacer login, linking o
  registro seguro
- las decisiones de seguridad importantes quedan aqui: no auto-merge agresivo
  por email salvo configuracion explicita, no linking silencioso con otra
  cuenta y no aceptar providers no configurados
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import transaction
from django.utils import timezone

from identity.social_identities.models import SocialAuthHandoff, UserSocialIdentity


class SocialOAuthError(ValueError):
    """Error de negocio o protocolo en el flujo social OAuth."""


@dataclass(slots=True)
class SocialAuthResult:
    user: object
    identity: UserSocialIdentity
    created_user: bool
    linked_identity: bool
    login_mode: str
    profile: dict
    token_data: dict
    state_payload: dict


SUPPORTED_SOCIAL_PROVIDERS = {
    "google": {
        "display_name": "Google",
        "authorize_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
        "scopes": ["openid", "email", "profile"],
    },
    "facebook": {
        "display_name": "Facebook",
        "authorize_endpoint": "https://www.facebook.com/v19.0/dialog/oauth",
        "token_endpoint": "https://graph.facebook.com/v19.0/oauth/access_token",
        "userinfo_endpoint": "https://graph.facebook.com/me",
        "scopes": ["email", "public_profile"],
    },
}


def get_social_provider_settings(provider: str) -> dict:
    provider_code = str(provider or "").strip().lower()
    if provider_code not in SUPPORTED_SOCIAL_PROVIDERS:
        raise ValueError(f"Proveedor OAuth no soportado: {provider}")

    client_id = getattr(settings, f"{provider_code.upper()}_OAUTH_CLIENT_ID", "")
    callback_url = getattr(settings, f"{provider_code.upper()}_OAUTH_CALLBACK_URL", "")
    frontend_callback_url = getattr(settings, f"{provider_code.upper()}_OAUTH_FRONTEND_CALLBACK_URL", "")
    client_secret = getattr(settings, f"{provider_code.upper()}_OAUTH_CLIENT_SECRET", "")
    scopes = list(SUPPORTED_SOCIAL_PROVIDERS[provider_code]["scopes"])
    enabled = bool(getattr(settings, f"{provider_code.upper()}_OAUTH_ENABLED", False))
    configured = bool(enabled and client_id and client_secret and (frontend_callback_url or callback_url))

    return {
        "provider": provider_code,
        "display_name": SUPPORTED_SOCIAL_PROVIDERS[provider_code]["display_name"],
        "authorize_endpoint": SUPPORTED_SOCIAL_PROVIDERS[provider_code]["authorize_endpoint"],
        "token_endpoint": SUPPORTED_SOCIAL_PROVIDERS[provider_code]["token_endpoint"],
        "userinfo_endpoint": SUPPORTED_SOCIAL_PROVIDERS[provider_code]["userinfo_endpoint"],
        "scopes": scopes,
        "client_id": client_id,
        "client_secret": client_secret,
        "callback_url": callback_url,
        "frontend_callback_url": frontend_callback_url,
        "enabled": enabled,
        "configured": configured,
        "identity_platform_enabled": bool(getattr(settings, "GCP_IDENTITY_PLATFORM_ENABLED", False)),
    }


def resolve_social_redirect_uri(provider: str, requested_redirect_uri: str = "") -> str:
    config = get_social_provider_settings(provider)
    requested = str(requested_redirect_uri or "").strip()
    allowed = {
        str(config.get("frontend_callback_url") or "").strip(),
        str(config.get("callback_url") or "").strip(),
    }
    allowed.discard("")
    if requested:
        if requested not in allowed:
            raise SocialOAuthError("redirect_uri no autorizado para el proveedor solicitado.")
        return requested
    return str(config.get("frontend_callback_url") or config.get("callback_url") or "").strip()


def _social_state_signer():
    return signing.TimestampSigner(salt=getattr(settings, "IDENTITY_SOCIAL_STATE_SALT", "identity-social-oauth"))


def build_social_state(*, provider: str, current_user=None, mode: str = "login", next_url: str = "", redirect_uri: str = "") -> str:
    payload = {
        "provider": provider,
        "mode": mode,
        "user_id": str(current_user.pk) if current_user is not None and getattr(current_user, "is_authenticated", False) else "",
        "next_url": next_url or "",
        "redirect_uri": redirect_uri or "",
        "nonce": secrets.token_urlsafe(16),
        "issued_at": timezone.now().isoformat(),
    }
    return _social_state_signer().sign_object(payload)


def parse_social_state(provider: str, state: str) -> dict:
    if not state:
        raise SocialOAuthError("Falta el parametro state del flujo social.")
    try:
        payload = _social_state_signer().unsign_object(
            state,
            max_age=int(getattr(settings, "IDENTITY_SOCIAL_STATE_MAX_AGE_SECONDS", 600)),
        )
    except signing.BadSignature as exc:
        raise SocialOAuthError("State OAuth invalido o expirado.") from exc
    if str(payload.get("provider") or "").strip().lower() != str(provider or "").strip().lower():
        raise SocialOAuthError("El state no corresponde al proveedor solicitado.")
    return payload


def build_social_authorization_url(provider: str, *, state: str = "vexxo-social", redirect_uri: str = "") -> str:
    data = get_social_provider_settings(provider)
    if not data["configured"]:
        return ""
    final_redirect_uri = resolve_social_redirect_uri(provider, redirect_uri)

    params = {
        "client_id": data["client_id"],
        "redirect_uri": final_redirect_uri,
        "response_type": "code",
        "scope": " ".join(data["scopes"]),
        "state": state,
    }
    if provider == "google":
        params["prompt"] = "consent"
    if provider == "facebook":
        params["auth_type"] = "rerequest"
    return f"{data['authorize_endpoint']}?{urlencode(params)}"


def _http_json(*, url: str, method: str = "GET", data: dict | None = None, headers: dict | None = None) -> dict:
    encoded = None
    request_headers = dict(headers or {})
    if data is not None:
        encoded = urlencode(data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = Request(url=url, data=encoded, headers=request_headers, method=method)
    try:
        with urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw or "{}")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise SocialOAuthError(f"OAuth provider respondio con error HTTP {exc.code}: {body[:250]}") from exc
    except URLError as exc:
        raise SocialOAuthError(f"No fue posible contactar el proveedor OAuth: {exc}") from exc


def exchange_social_code(*, provider: str, code: str, redirect_uri: str = "") -> dict:
    if not code:
        raise SocialOAuthError("Falta el parametro code del callback OAuth.")
    config = get_social_provider_settings(provider)
    if not config["configured"]:
        raise SocialOAuthError("El proveedor OAuth aun no esta configurado.")
    final_redirect_uri = resolve_social_redirect_uri(provider, redirect_uri)
    payload = {
        "code": code,
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "redirect_uri": final_redirect_uri,
        "grant_type": "authorization_code",
    }
    if provider == "facebook":
        payload.pop("grant_type", None)
    return _http_json(url=config["token_endpoint"], method="POST", data=payload)


def fetch_social_profile(*, provider: str, token_data: dict) -> dict:
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise SocialOAuthError("El proveedor no devolvio access_token.")
    config = get_social_provider_settings(provider)
    if provider == "google":
        profile = _http_json(
            url=config["userinfo_endpoint"],
            method="GET",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return {
            "provider_user_id": str(profile.get("sub") or ""),
            "email": str(profile.get("email") or "").strip().lower(),
            "email_verified": bool(profile.get("email_verified")),
            "full_name": str(profile.get("name") or "").strip(),
            "first_name": str(profile.get("given_name") or "").strip(),
            "last_name": str(profile.get("family_name") or "").strip(),
            "avatar_url": str(profile.get("picture") or "").strip(),
            "raw": profile,
        }

    profile = _http_json(
        url=f"{config['userinfo_endpoint']}?{urlencode({'fields': 'id,name,email,first_name,last_name,picture.type(large)', 'access_token': access_token})}",
        method="GET",
    )
    picture = ((profile.get("picture") or {}).get("data") or {}).get("url", "")
    return {
        "provider_user_id": str(profile.get("id") or ""),
        "email": str(profile.get("email") or "").strip().lower(),
        "email_verified": bool(profile.get("email")),
        "full_name": str(profile.get("name") or "").strip(),
        "first_name": str(profile.get("first_name") or "").strip(),
        "last_name": str(profile.get("last_name") or "").strip(),
        "avatar_url": str(picture or "").strip(),
        "raw": profile,
    }


def _split_name(full_name: str) -> tuple[str, str]:
    parts = [part for part in str(full_name or "").strip().split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _build_unique_username(base: str) -> str:
    User = get_user_model()
    clean = "".join(ch.lower() if ch.isalnum() else "." for ch in base or "social.user").strip(".")
    clean = clean or "social.user"
    candidate = clean[:120]
    suffix = 1
    while User.objects.filter(username=candidate).exists():
        suffix += 1
        candidate = f"{clean[:110]}.{suffix}"
    return candidate


def _create_user_from_social_profile(*, provider: str, profile: dict):
    User = get_user_model()
    email = str(profile.get("email") or "").strip().lower()
    full_name = str(profile.get("full_name") or "").strip()
    first_name = str(profile.get("first_name") or "").strip()
    last_name = str(profile.get("last_name") or "").strip()
    if not first_name and not last_name:
        first_name, last_name = _split_name(full_name)
    username_seed = email.split("@", 1)[0] if email else f"{provider}.user"
    user = User.objects.create_user(
        username=_build_unique_username(username_seed),
        email=email or f"{provider}.{secrets.token_hex(8)}@pending.vexxo.local",
        password=secrets.token_urlsafe(24),
        first_name=first_name,
        last_name=last_name,
    )
    if hasattr(user, "is_verified") and profile.get("email_verified"):
        user.is_verified = True
        user.save(update_fields=["is_verified", "updated_at"])
    return user


def upsert_social_identity(*, user, provider: str, profile: dict) -> tuple[UserSocialIdentity, bool]:
    provider_user_id = str(profile.get("provider_user_id") or "").strip()
    if not provider_user_id:
        raise SocialOAuthError("El perfil remoto no devolvio un identificador util.")
    identity, created = UserSocialIdentity.objects.update_or_create(
        provider=provider,
        provider_user_id=provider_user_id,
        defaults={
            "user": user,
            "email": str(profile.get("email") or "").strip().lower(),
            "email_verified": bool(profile.get("email_verified")),
            "full_name": str(profile.get("full_name") or user.display_name),
            "avatar_url": str(profile.get("avatar_url") or ""),
            "is_active": True,
            "unlinked_at": None,
            "metadata": dict(profile.get("raw") or {}),
        },
    )
    identity.touch_login(commit=True)
    return identity, created


def unlink_social_identity(*, user, provider: str) -> UserSocialIdentity:
    identity = UserSocialIdentity.objects.filter(user=user, provider=provider, is_active=True).first()
    if identity is None:
        raise SocialOAuthError("No existe una identidad social activa para ese proveedor.")
    identity.unlink(commit=True)
    return identity


def create_social_auth_handoff(*, result: SocialAuthResult) -> SocialAuthHandoff:
    handoff = SocialAuthHandoff.objects.create(
        code=secrets.token_urlsafe(32),
        provider=result.identity.provider,
        user=result.user,
        identity=result.identity,
        login_mode=result.login_mode,
        created_user=result.created_user,
        linked_identity=result.linked_identity,
        expires_at=timezone.now() + timedelta(minutes=5),
        metadata={
            "email": str(result.profile.get("email") or result.user.email),
            "provider_user_id": str(result.profile.get("provider_user_id") or ""),
            "state_payload": dict(result.state_payload or {}),
        },
    )
    return handoff


def consume_social_auth_handoff(*, code: str) -> SocialAuthHandoff:
    now = timezone.now()
    with transaction.atomic():
        handoff = (
            SocialAuthHandoff.objects.select_for_update()
            .select_related("user", "identity")
            .filter(code=code)
            .first()
        )
        if handoff is None:
            raise SocialOAuthError("Handoff social no encontrado.")
        if handoff.used_at is not None:
            raise SocialOAuthError("Handoff social ya consumido.")
        if handoff.expires_at < now:
            raise SocialOAuthError("Handoff social expirado.")
        updated = SocialAuthHandoff.objects.filter(
            pk=handoff.pk,
            used_at__isnull=True,
            expires_at__gte=now,
        ).update(used_at=now, updated_at=now)
        if updated != 1:
            raise SocialOAuthError("Handoff social ya consumido o invalido.")
        handoff.used_at = now
        handoff.updated_at = now
        return handoff


def resolve_social_callback(*, provider: str, code: str, state: str, current_user=None, redirect_uri: str = "") -> SocialAuthResult:
    provider = str(provider or "").strip().lower()
    state_payload = parse_social_state(provider, state)
    expected_redirect_uri = str(state_payload.get("redirect_uri") or "").strip()
    if redirect_uri and expected_redirect_uri and str(redirect_uri).strip() != expected_redirect_uri:
        raise SocialOAuthError("redirect_uri no coincide con el flujo social firmado.")
    if str(state_payload.get("mode") or "") == "link" and not (
        current_user is not None and getattr(current_user, "is_authenticated", False)
    ):
        raise SocialOAuthError("El callback de vinculacion requiere un usuario autenticado.")
    token_data = exchange_social_code(
        provider=provider,
        code=code,
        redirect_uri=redirect_uri or expected_redirect_uri,
    )
    profile = fetch_social_profile(provider=provider, token_data=token_data)
    provider_user_id = str(profile.get("provider_user_id") or "").strip()
    email = str(profile.get("email") or "").strip().lower()
    existing_identity = UserSocialIdentity.objects.filter(
        provider=provider,
        provider_user_id=provider_user_id,
    ).select_related("user").first()

    login_mode = str(state_payload.get("mode") or "login")
    created_user = False
    linked_identity = False

    if current_user is not None and getattr(current_user, "is_authenticated", False):
        expected_user_id = str(state_payload.get("user_id") or "")
        if expected_user_id and expected_user_id != str(current_user.pk):
            raise SocialOAuthError("El state OAuth no corresponde al usuario autenticado.")
        if existing_identity and existing_identity.user_id != current_user.pk:
            raise SocialOAuthError("La identidad social ya esta vinculada a otro usuario.")
        user = current_user
        identity, linked_identity = upsert_social_identity(user=user, provider=provider, profile=profile)
        return SocialAuthResult(
            user=user,
            identity=identity,
            created_user=False,
            linked_identity=linked_identity,
            login_mode="link",
            profile=profile,
            token_data=token_data,
            state_payload=state_payload,
        )

    if existing_identity and existing_identity.is_active:
        user = existing_identity.user
        existing_identity.touch_login(commit=True)
        return SocialAuthResult(
            user=user,
            identity=existing_identity,
            created_user=False,
            linked_identity=False,
            login_mode="login_existing_identity",
            profile=profile,
            token_data=token_data,
            state_payload=state_payload,
        )

    User = get_user_model()
    existing_user = User.objects.filter(email__iexact=email).first() if email else None
    if existing_user and not bool(getattr(settings, "IDENTITY_SOCIAL_AUTO_LINK_BY_EMAIL", False)):
        raise SocialOAuthError(
            "Ya existe un usuario con ese email. Inicia sesion primero y vincula el proveedor desde tu perfil."
        )

    user = existing_user
    if user is None:
        user = _create_user_from_social_profile(provider=provider, profile=profile)
        created_user = True

    identity, linked_identity = upsert_social_identity(user=user, provider=provider, profile=profile)
    return SocialAuthResult(
        user=user,
        identity=identity,
        created_user=created_user,
        linked_identity=linked_identity,
        login_mode="register" if created_user else "login_existing_email",
        profile=profile,
        token_data=token_data,
        state_payload=state_payload,
    )


def get_supported_social_providers() -> list[dict]:
    providers = []
    for provider in SUPPORTED_SOCIAL_PROVIDERS:
        data = get_social_provider_settings(provider)
        data["authorization_url"] = build_social_authorization_url(
            provider,
            state=build_social_state(
                provider=provider,
                redirect_uri=resolve_social_redirect_uri(provider),
            ),
            redirect_uri=resolve_social_redirect_uri(provider),
        )
        providers.append(data)
    return providers
