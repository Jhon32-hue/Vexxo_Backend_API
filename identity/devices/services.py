from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from common.domain_events import EventPriority
from identity.devices.attestation import PlatformAttestationError, decode_play_integrity_token, verify_app_attest_object
from identity.devices.models import (
    DeviceAttestationStatus,
    DevicePlatformAttestationChallenge,
    DeviceSignatureChallenge,
    DeviceTrustLevel,
    UserDevice,
)
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
            "signing_algorithm": payload.get("signing_algorithm", ""),
            "signing_public_key": payload.get("signing_public_key", ""),
            "attestation_status": DeviceAttestationStatus.PENDING if payload.get("signing_public_key") else DeviceAttestationStatus.UNAVAILABLE,
        },
    )
    if not created:
        dirty_fields = []
        for field in ["external_device_id", "name", "device_type", "platform", "os_version", "app_version", "push_token", "locale", "timezone_name"]:
            incoming = payload.get(field)
            if incoming not in (None, "") and getattr(device, field) != incoming:
                setattr(device, field, incoming)
                dirty_fields.append(field)
        incoming_public_key = str(payload.get("signing_public_key") or "")
        incoming_algorithm = str(payload.get("signing_algorithm") or "")
        if incoming_public_key and incoming_public_key != device.signing_public_key:
            device.signing_public_key = incoming_public_key
            device.signing_algorithm = incoming_algorithm
            device.key_verified_at = None
            device.attestation_status = DeviceAttestationStatus.PENDING
            dirty_fields.extend(["signing_public_key", "signing_algorithm", "key_verified_at", "attestation_status"])
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


def issue_signature_challenge(*, device: UserDevice, purpose: str) -> tuple[DeviceSignatureChallenge, str]:
    if not device.is_active or not device.signing_public_key or device.signing_algorithm != "ed25519":
        raise ValueError("device_key_unavailable")
    nonce_bytes = secrets.token_bytes(32)
    nonce = base64.urlsafe_b64encode(nonce_bytes).decode("ascii").rstrip("=")
    challenge = DeviceSignatureChallenge.objects.create(
        device=device,
        purpose=purpose,
        nonce_hash=hashlib.sha256(nonce_bytes).hexdigest(),
        expires_at=timezone.now() + timedelta(minutes=3),
    )
    return challenge, nonce


@transaction.atomic
def verify_signature_challenge(
    *,
    device: UserDevice,
    challenge_id,
    nonce: str,
    signature: str,
    purpose: str,
) -> DeviceSignatureChallenge:
    challenge = DeviceSignatureChallenge.objects.select_for_update().filter(
        public_id=challenge_id,
        device=device,
        purpose=purpose,
    ).first()
    if challenge is None or challenge.consumed_at is not None or challenge.expires_at <= timezone.now():
        raise ValueError("challenge_invalid_or_expired")
    if challenge.failed_attempts >= 5:
        raise ValueError("challenge_locked")
    try:
        nonce_bytes = base64.urlsafe_b64decode(str(nonce) + "=" * (-len(str(nonce)) % 4))
        signature_bytes = base64.b64decode(signature, validate=True)
        public_key_bytes = base64.b64decode(device.signing_public_key, validate=True)
    except ValueError:
        nonce_bytes = b""
        signature_bytes = b""
        public_key_bytes = b""
    valid_nonce = secrets.compare_digest(hashlib.sha256(nonce_bytes).hexdigest(), challenge.nonce_hash)
    try:
        if not valid_nonce:
            raise InvalidSignature
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature_bytes, nonce_bytes)
    except (InvalidSignature, ValueError):
        challenge.failed_attempts += 1
        challenge.save(update_fields=["failed_attempts"])
        raise ValueError("invalid_signature")

    now = timezone.now()
    challenge.consumed_at = now
    challenge.save(update_fields=["consumed_at"])
    device.key_verified_at = now
    if device.attestation_status != DeviceAttestationStatus.PLATFORM_VERIFIED:
        device.attestation_status = DeviceAttestationStatus.KEY_VERIFIED
    device.save(update_fields=["key_verified_at", "attestation_status", "updated_at"])
    return challenge


def platform_attestation_configuration(provider: str) -> dict:
    provider = str(provider or "").strip().lower()
    if provider == DevicePlatformAttestationChallenge.Provider.PLAY_INTEGRITY:
        cloud_project_number = str(getattr(settings, "PLAY_INTEGRITY_CLOUD_PROJECT_NUMBER", "") or "").strip()
        configured = bool(
            cloud_project_number
            and getattr(settings, "PLAY_INTEGRITY_PACKAGE_NAMES", [])
            and str(getattr(settings, "PLAY_INTEGRITY_SERVICE_ACCOUNT_JSON", "") or "").strip()
        )
        return {
            "provider": provider,
            "configured": configured,
            "cloud_project_number": cloud_project_number if configured else "",
        }
    if provider == DevicePlatformAttestationChallenge.Provider.APP_ATTEST:
        configured = bool(
            str(getattr(settings, "APPLE_APP_ATTEST_APP_ID", "") or "").strip()
            and str(getattr(settings, "APPLE_APP_ATTEST_ROOT_CA_PEM", "") or "").strip()
        )
        return {"provider": provider, "configured": configured}
    raise ValueError("unsupported_attestation_provider")


def issue_platform_attestation_challenge(
    *, device: UserDevice, provider: str
) -> tuple[DevicePlatformAttestationChallenge, str, dict]:
    configuration = platform_attestation_configuration(provider)
    if not configuration["configured"]:
        raise ImproperlyConfigured("platform_attestation_not_configured")
    if not device.is_active:
        raise ValueError("inactive_device")
    nonce_bytes = secrets.token_bytes(32)
    nonce = base64.urlsafe_b64encode(nonce_bytes).decode("ascii").rstrip("=")
    request_hash = hashlib.sha256(nonce_bytes).hexdigest()
    challenge = DevicePlatformAttestationChallenge.objects.create(
        device=device,
        provider=provider,
        nonce_hash=hashlib.sha256(nonce_bytes).hexdigest(),
        request_hash=request_hash,
        expires_at=timezone.now() + timedelta(minutes=3),
    )
    return challenge, nonce, configuration


def verify_platform_attestation(
    *, device: UserDevice, challenge_id, provider: str, nonce: str,
    token: str = "", key_id: str = "", attestation_object: str = "",
) -> DevicePlatformAttestationChallenge:
    challenge = DevicePlatformAttestationChallenge.objects.filter(
        public_id=challenge_id, device=device, provider=provider,
    ).first()
    if challenge is None or challenge.consumed_at is not None or challenge.expires_at <= timezone.now():
        raise ValueError("challenge_invalid_or_expired")
    if challenge.failed_attempts >= 3:
        raise ValueError("challenge_locked")
    try:
        nonce_bytes = base64.urlsafe_b64decode(str(nonce) + "=" * (-len(str(nonce)) % 4))
    except ValueError as exc:
        _record_challenge_failure(challenge=challenge, device=device, reason="invalid_nonce")
        raise ValueError("invalid_nonce") from exc
    if not secrets.compare_digest(hashlib.sha256(nonce_bytes).hexdigest(), challenge.nonce_hash):
        _record_challenge_failure(challenge=challenge, device=device, reason="invalid_nonce")
        raise ValueError("invalid_nonce")
    try:
        if provider == DevicePlatformAttestationChallenge.Provider.PLAY_INTEGRITY:
            result = decode_play_integrity_token(token=token, expected_request_hash=challenge.request_hash)
        elif provider == DevicePlatformAttestationChallenge.Provider.APP_ATTEST:
            result = verify_app_attest_object(
                attestation_object_b64=attestation_object,
                key_id=key_id,
                challenge_nonce=nonce_bytes,
            )
        else:
            raise ValueError("unsupported_attestation_provider")
    except PlatformAttestationError as exc:
        _record_challenge_failure(challenge=challenge, device=device, reason=str(exc))
        raise
    duplicate_attestation_key = False
    if result.key_id and UserDevice.objects.exclude(pk=device.pk).filter(attestation_key_id=result.key_id).exists():
        _record_challenge_failure(challenge=challenge, device=device, reason="attestation_key_already_registered")
        raise PlatformAttestationError("attestation_key_already_registered")
    with transaction.atomic():
        challenge = DevicePlatformAttestationChallenge.objects.select_for_update().get(pk=challenge.pk)
        device = UserDevice.objects.select_for_update().get(pk=device.pk)
        if challenge.consumed_at is not None or challenge.expires_at <= timezone.now() or challenge.failed_attempts >= 3:
            raise ValueError("challenge_invalid_or_expired")
        if result.key_id and UserDevice.objects.exclude(pk=device.pk).filter(attestation_key_id=result.key_id).exists():
            duplicate_attestation_key = True
        else:
            now = timezone.now()
            challenge.consumed_at = now
            challenge.save(update_fields=["consumed_at"])
            device.attestation_provider = result.provider
            device.attestation_status = DeviceAttestationStatus.PLATFORM_VERIFIED
            device.attestation_key_id = result.key_id
            device.attestation_public_key = result.public_key_b64
            device.attestation_counter = result.counter
            device.platform_verified_at = now
            device.platform_verification_expires_at = now + timedelta(
                days=max(1, int(getattr(settings, "DEVICE_ATTESTATION_VALIDITY_DAYS", 30)))
            )
            device.attestation_failure_count = 0
            device.save(update_fields=[
                "attestation_provider", "attestation_status", "attestation_key_id",
                "attestation_public_key", "attestation_counter", "platform_verified_at",
                "platform_verification_expires_at", "attestation_failure_count", "updated_at",
            ])
    if duplicate_attestation_key:
        _record_challenge_failure(challenge=challenge, device=device, reason="attestation_key_already_registered")
        raise PlatformAttestationError("attestation_key_already_registered")
    return challenge


@transaction.atomic
def _record_challenge_failure(*, challenge: DevicePlatformAttestationChallenge, device: UserDevice, reason: str) -> None:
    locked = DevicePlatformAttestationChallenge.objects.select_for_update().get(pk=challenge.pk)
    locked.failed_attempts += 1
    locked.save(update_fields=["failed_attempts"])
    _record_attestation_failure(device=device, reason=reason)


def _record_attestation_failure(*, device: UserDevice, reason: str) -> None:
    from identity.sessions.services import revoke_device_sessions
    from security.audit import record_security_event
    from security.models import SecurityAuditEvent

    device = UserDevice.objects.select_for_update().get(pk=device.pk)
    device.attestation_failure_count += 1
    device.last_attestation_failure_at = timezone.now()
    threshold = max(1, int(getattr(settings, "DEVICE_ATTESTATION_FAILURE_THRESHOLD", 3)))
    update_fields = ["attestation_failure_count", "last_attestation_failure_at", "updated_at"]
    if device.attestation_failure_count >= threshold:
        device.attestation_status = DeviceAttestationStatus.REJECTED
        device.trust_level = DeviceTrustLevel.SUSPICIOUS
        update_fields.extend(["attestation_status", "trust_level"])
    device.save(update_fields=update_fields)
    if device.attestation_failure_count >= threshold:
        revoke_device_sessions(device_id=device.pk, reason="attestation_anomaly")
    record_security_event(
        event_type="identity.device.attestation_failed",
        severity=SecurityAuditEvent.Severity.CRITICAL if device.attestation_failure_count >= threshold else SecurityAuditEvent.Severity.WARNING,
        actor=device.user,
        source="identity.devices",
        target_type="device",
        target_id=str(device.pk),
        metadata={"reason_code": reason[:64], "failure_count": device.attestation_failure_count},
    )


def expire_platform_attestations(*, now=None) -> dict:
    now = now or timezone.now()
    devices = list(UserDevice.objects.filter(
        attestation_status=DeviceAttestationStatus.PLATFORM_VERIFIED,
        platform_verification_expires_at__lte=now,
    ))
    for device in devices:
        device.attestation_status = (
            DeviceAttestationStatus.KEY_VERIFIED if device.key_verified_at else DeviceAttestationStatus.PENDING
        )
        device.save(update_fields=["attestation_status", "updated_at"])
    return {"expired_attestations": len(devices)}


def revoke_platform_attestations(*, provider: str = "", verified_before=None) -> int:
    from identity.sessions.services import revoke_device_sessions

    queryset = UserDevice.objects.filter(attestation_status=DeviceAttestationStatus.PLATFORM_VERIFIED)
    if provider:
        queryset = queryset.filter(attestation_provider=provider)
    if verified_before:
        queryset = queryset.filter(platform_verified_at__lt=verified_before)
    devices = list(queryset)
    for device in devices:
        device.attestation_status = DeviceAttestationStatus.REJECTED
        device.platform_verification_expires_at = timezone.now()
        device.save(update_fields=["attestation_status", "platform_verification_expires_at", "updated_at"])
        revoke_device_sessions(device_id=device.pk, reason="attestation_bulk_revoked")
    return len(devices)


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
    from identity.sessions.services import revoke_device_sessions

    device.revoke(commit=True)
    revoke_device_sessions(device_id=device.pk, reason="device_revoked")
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
