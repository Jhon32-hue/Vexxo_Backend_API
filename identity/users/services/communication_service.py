"""
Servicios simples de correo transaccional y preferencias de comunicacion.
"""

from __future__ import annotations

from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from notifications.deliveries.models import NotificationChannel, NotificationStatus
from notifications.deliveries.services import create_notification_delivery
from notifications.preferences.services import get_or_create_notification_preferences
from security.validators import validate_https_url


def _resolve_from_email() -> str:
    return str(
        getattr(settings, "DEFAULT_FROM_EMAIL", "")
        or getattr(settings, "EMAIL_HOST_USER", "")
        or "no-reply@vexxo.local"
    )


def _resolve_frontend_url(base_url: str, params: dict[str, str]) -> str:
    normalized = str(base_url or "").strip()
    if not normalized:
        return ""
    if "{uid}" in normalized or "{token}" in normalized:
        return normalized.format(**params)
    separator = "&" if "?" in normalized else "?"
    return f"{normalized}{separator}{urlencode(params)}"


def _resolve_password_reset_base_url(requested_url: str) -> str:
    configured = str(
        getattr(settings, "IDENTITY_PASSWORD_RESET_FRONTEND_URL", "")
        or getattr(settings, "APP_FRONTEND_URL", "")
        or ""
    ).strip()
    candidate = str(requested_url or configured).strip()
    if not candidate:
        return ""
    allowed_hosts = set(getattr(settings, "IDENTITY_PASSWORD_RESET_ALLOWED_HOSTS", []) or [])
    configured_host = urlparse(configured).hostname
    if configured_host:
        allowed_hosts.add(configured_host.lower())
    if requested_url and not allowed_hosts:
        return ""
    try:
        return validate_https_url(
            candidate,
            allowed_hosts=allowed_hosts,
            allow_http_local=getattr(settings, "BOOT_ENV", "local") == "local",
        )
    except ValidationError:
        if requested_url and configured and requested_url != configured:
            return _resolve_password_reset_base_url("")
        return ""


def _can_send_lifecycle_email(user) -> bool:
    preferences = get_or_create_notification_preferences(user)
    return bool(preferences.email_notifications_enabled)


def _can_send_marketing_email(user) -> bool:
    preferences = get_or_create_notification_preferences(user)
    return bool(preferences.email_marketing_enabled and preferences.newsletter_subscribed)


def send_transactional_email(
    *,
    user,
    subject: str,
    message: str,
    source: str,
    event_type: str,
    dedupe_key: str,
    payload: dict | None = None,
    respect_notifications_preference: bool = True,
):
    payload = payload or {}
    if respect_notifications_preference and not _can_send_lifecycle_email(user):
        return None

    delivery = create_notification_delivery(
        owner=user,
        title=subject[:180],
        message=message,
        event_type=event_type,
        source=source,
        payload=payload,
        channel=NotificationChannel.EMAIL,
        dedupe_key=dedupe_key,
        mark_delivered_immediately=False,
    )
    if delivery.status == NotificationStatus.DELIVERED:
        return delivery

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=_resolve_from_email(),
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as exc:
        delivery.payload = {
            **(delivery.payload or {}),
            "send_error": str(exc),
        }
        delivery.mark_failed(commit=False)
        delivery.save(update_fields=["status", "payload", "updated_at"])
        return delivery

    delivery.mark_delivered()
    return delivery


def send_password_reset_email(*, user, redirect_url: str = ""):
    token = PasswordResetTokenGenerator().make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    reset_url = _resolve_frontend_url(_resolve_password_reset_base_url(redirect_url), {"uid": uid, "token": token})
    message = (
        f"Hola {user.display_name},\n\n"
        "Recibimos una solicitud para restablecer tu contrasena en Vexxo.\n"
        f"Enlace: {reset_url or 'Configura IDENTITY_PASSWORD_RESET_FRONTEND_URL para exponer un enlace directo.'}\n\n"
        "Si no hiciste esta solicitud, puedes ignorar este correo."
    )
    delivery = send_transactional_email(
        user=user,
        subject="Recupera tu acceso a Vexxo",
        message=message,
        source="identity.users.communication.password_reset",
        event_type="users.password_reset.requested.v1",
        dedupe_key="",
        payload={"uid": uid, "has_frontend_reset_url": bool(reset_url)},
        respect_notifications_preference=False,
    )
    return {
        "delivery": delivery,
        "uid": uid,
        "token": token,
        "reset_url": reset_url,
    }


def send_welcome_email_if_needed(user):
    preferences = get_or_create_notification_preferences(user)
    if preferences.welcome_email_sent_at is not None:
        return None
    if not preferences.email_notifications_enabled:
        return None

    frontend_url = str(getattr(settings, "APP_FRONTEND_URL", "") or "").strip()
    message = (
        f"Hola {user.display_name},\n\n"
        "Bienvenido a Vexxo. Tu espacio base ya esta listo para empezar a organizar tu vida financiera.\n"
        f"Continua aqui: {frontend_url or '/onboarding'}"
    )
    delivery = send_transactional_email(
        user=user,
        subject="Bienvenido a Vexxo",
        message=message,
        source="identity.users.communication.welcome_email",
        event_type="users.welcome_email.sent.v1",
        dedupe_key=f"users.welcome_email:{user.pk}",
        payload={"frontend_url": frontend_url or "/onboarding"},
        respect_notifications_preference=True,
    )
    if delivery is not None and delivery.status == NotificationStatus.DELIVERED:
        preferences.welcome_email_sent_at = timezone.now()
        preferences.save(update_fields=["welcome_email_sent_at", "updated_at"])
    return delivery


def update_marketing_preferences(*, user, newsletter_subscribed: bool, email_marketing_enabled: bool):
    preferences = get_or_create_notification_preferences(user)
    preferences.newsletter_subscribed = bool(newsletter_subscribed)
    preferences.email_marketing_enabled = bool(email_marketing_enabled)
    preferences.save(
        update_fields=[
            "newsletter_subscribed",
            "email_marketing_enabled",
            "updated_at",
        ]
    )
    marketing_opt_in = bool(preferences.newsletter_subscribed and preferences.email_marketing_enabled)
    if user.marketing_opt_in != marketing_opt_in:
        user.marketing_opt_in = marketing_opt_in
        user.save(update_fields=["marketing_opt_in", "updated_at"])
    return preferences
