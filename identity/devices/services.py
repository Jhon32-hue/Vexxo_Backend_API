from __future__ import annotations

from django.db.models import Count
from django.utils import timezone

from common.domain_events import EventPriority
from identity.devices.models import DeviceTrustLevel, UserDevice
from identity.users.domain import UserDomainEventTypes, build_identity_entity_payload
from identity.users.services.event_service import publish_user_event_after_commit


def _request_ip(request) -> str | None:
    if not request:
        return None
    ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR")
    if not ip:
        return None
    return ip.split(",")[0].strip() if "," in ip else ip


def register_or_update_device(*, user, request=None, payload: dict | None = None) -> UserDevice:
    payload = payload or {}
    fingerprint = payload.get("fingerprint") or request.headers.get("X-Device-Fingerprint") or "web-anonymous"
    device, created = UserDevice.objects.get_or_create(
        user=user,
        fingerprint=fingerprint,
        defaults={
            "external_device_id": payload.get("external_device_id", ""),
            "name": payload.get("name", ""),
            "device_type": payload.get("device_type", "web"),
            "platform": payload.get("platform", ""),
            "os_version": payload.get("os_version", ""),
            "app_version": payload.get("app_version", ""),
            "push_token": payload.get("push_token", ""),
            "locale": payload.get("locale", getattr(user, "locale", "")),
            "timezone_name": payload.get("timezone_name", getattr(user, "timezone_name", "")),
            "user_agent": request.META.get("HTTP_USER_AGENT", "") if request else "",
            "ip_address": _request_ip(request),
            "metadata": payload.get("metadata", {}),
        },
    )
    if not created:
        dirty_fields = []
        for field in ["external_device_id", "name", "device_type", "platform", "os_version", "app_version", "push_token", "locale", "timezone_name"]:
            incoming = payload.get(field)
            if incoming not in (None, "") and getattr(device, field) != incoming:
                setattr(device, field, incoming)
                dirty_fields.append(field)
        if request:
            user_agent = request.META.get("HTTP_USER_AGENT", "")
            ip_address = _request_ip(request)
            if user_agent and device.user_agent != user_agent:
                device.user_agent = user_agent
                dirty_fields.append("user_agent")
            if ip_address and str(device.ip_address or "") != str(ip_address):
                device.ip_address = ip_address
                dirty_fields.append("ip_address")
        device.last_seen_at = timezone.now()
        dirty_fields.extend(["last_seen_at", "updated_at"])
        device.save(update_fields=list(dict.fromkeys(dirty_fields)))

    publish_user_event_after_commit(
        event_type=UserDomainEventTypes.USER_DEVICE_REGISTERED,
        payload=build_identity_entity_payload(
            user=user,
            entity_type="device",
            entity_id=device.pk,
            extra={
                "fingerprint": device.fingerprint,
                "device_type": device.device_type,
                "trust_level": device.trust_level,
                "created": created,
            },
        ),
        metadata={"source": "identity.devices.register_or_update_device"},
        priority=EventPriority.NORMAL,
    )
    return device


def trust_device(device: UserDevice) -> UserDevice:
    device.mark_trusted(commit=True)
    publish_user_event_after_commit(
        event_type=UserDomainEventTypes.USER_DEVICE_TRUSTED,
        payload=build_identity_entity_payload(
            user=device.user,
            entity_type="device",
            entity_id=device.pk,
            extra={"trust_level": DeviceTrustLevel.TRUSTED},
        ),
        metadata={"source": "identity.devices.trust_device"},
        priority=EventPriority.NORMAL,
    )
    return device


def revoke_device(device: UserDevice) -> UserDevice:
    device.revoke(commit=True)
    publish_user_event_after_commit(
        event_type=UserDomainEventTypes.USER_DEVICE_REVOKED,
        payload=build_identity_entity_payload(
            user=device.user,
            entity_type="device",
            entity_id=device.pk,
            extra={"trust_level": device.trust_level},
        ),
        metadata={"source": "identity.devices.revoke_device"},
        priority=EventPriority.HIGH,
    )
    return device


def device_summary_for_user(user) -> dict:
    base_qs = UserDevice.objects.filter(user=user)
    trust_counts = {
        row["trust_level"]: row["total"]
        for row in base_qs.values("trust_level").annotate(total=Count("id"))
    }
    return {
        "user_id": str(user.pk),
        "total_devices": base_qs.count(),
        "active_devices": base_qs.filter(is_active=True).count(),
        "trusted_devices": trust_counts.get(DeviceTrustLevel.TRUSTED, 0),
        "unknown_devices": trust_counts.get(DeviceTrustLevel.UNKNOWN, 0),
        "suspicious_devices": trust_counts.get(DeviceTrustLevel.SUSPICIOUS, 0),
        "blocked_devices": trust_counts.get(DeviceTrustLevel.BLOCKED, 0),
        "primary_devices": base_qs.filter(is_primary=True, is_active=True).count(),
        "devices_by_type": {
            row["device_type"] or "unknown": row["total"]
            for row in base_qs.values("device_type").annotate(total=Count("id"))
        },
        "devices_by_trust": trust_counts,
    }
