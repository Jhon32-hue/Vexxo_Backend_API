"""
Adapter externo de mensajeria para codigos cortos y futuros magic links.
"""

from __future__ import annotations

from django.conf import settings

from notifications.deliveries.models import NotificationChannel
from notifications.deliveries.services import create_notification_delivery


def dispatch_identity_message(
    *,
    owner,
    subject: str,
    message: str,
    event_type: str,
    source: str,
    payload: dict | None = None,
    debug_code: str = "",
):
    payload = dict(payload or {})
    backend = str(getattr(settings, "IDENTITY_MESSAGE_BACKEND", "local_stub") or "local_stub").strip()
    transport = str(getattr(settings, "IDENTITY_MESSAGE_TRANSPORT", "sms") or "sms").strip()
    payload["dispatch_backend"] = backend
    payload["transport"] = transport
    if debug_code and bool(getattr(settings, "IDENTITY_RECOVERY_DEBUG_REVEAL_CODE", False)):
        payload["debug_code"] = debug_code

    delivery = create_notification_delivery(
        owner=owner,
        title=subject,
        message=message,
        event_type=event_type,
        source=source,
        payload=payload,
        channel=NotificationChannel.SYSTEM,
        dedupe_key="",
        mark_delivered_immediately=False,
    )

    if backend in {"local_stub", "sms_stub", "whatsapp_stub"}:
        delivery.payload = payload
        delivery.mark_delivered(commit=False)
        delivery.save(update_fields=["status", "delivered_at", "payload", "updated_at"])
        return delivery

    delivery.payload = {
        **payload,
        "dispatch_error": f"identity message backend `{backend}` no implementado en este runtime",
    }
    delivery.mark_failed(commit=False)
    delivery.save(update_fields=["status", "payload", "updated_at"])
    return delivery
