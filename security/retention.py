from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from security.models import SecurityAuditEvent, SecurityThrottleBucket


def _delete_ids(queryset, *, limit: int) -> int:
    ids = list(queryset.order_by("pk").values_list("pk", flat=True)[:limit])
    if not ids:
        return 0
    deleted, _ = queryset.model._default_manager.filter(pk__in=ids).delete()
    return deleted


@transaction.atomic
def purge_security_retention(*, limit_per_model: int = 500, now=None) -> dict:
    from documents.files.models import DocumentDownloadGrant
    from identity.devices.models import DevicePlatformAttestationChallenge, DeviceSignatureChallenge
    from identity.users.models import UserAuthChallenge

    now = now or timezone.now()
    limit = max(1, min(int(limit_per_model), 5000))
    audit_days = {
        SecurityAuditEvent.Severity.INFO: int(getattr(settings, "SECURITY_AUDIT_INFO_RETENTION_DAYS", 365)),
        SecurityAuditEvent.Severity.WARNING: int(getattr(settings, "SECURITY_AUDIT_WARNING_RETENTION_DAYS", 730)),
        SecurityAuditEvent.Severity.CRITICAL: int(getattr(settings, "SECURITY_AUDIT_CRITICAL_RETENTION_DAYS", 2555)),
    }
    result = {}
    for severity, days in audit_days.items():
        result[f"audit_{severity}"] = _delete_ids(
            SecurityAuditEvent.objects.filter(severity=severity, created_at__lt=now - timedelta(days=max(1, days))),
            limit=limit,
        )
    throttle_days = int(getattr(settings, "SECURITY_THROTTLE_RETENTION_DAYS", 30))
    result["throttle_buckets"] = _delete_ids(
        SecurityThrottleBucket.objects.filter(updated_at__lt=now - timedelta(days=max(1, throttle_days))).filter(Q(blocked_until__isnull=True) | Q(blocked_until__lt=now)),
        limit=limit,
    )
    challenge_cutoff = now - timedelta(days=int(getattr(settings, "SECURITY_CHALLENGE_RETENTION_DAYS", 30)))
    result["auth_challenges"] = _delete_ids(UserAuthChallenge.objects.filter(updated_at__lt=challenge_cutoff), limit=limit)
    result["signature_challenges"] = _delete_ids(DeviceSignatureChallenge.objects.filter(created_at__lt=challenge_cutoff), limit=limit)
    result["attestation_challenges"] = _delete_ids(DevicePlatformAttestationChallenge.objects.filter(created_at__lt=challenge_cutoff), limit=limit)
    result["download_grants"] = _delete_ids(DocumentDownloadGrant.objects.filter(expires_at__lt=challenge_cutoff), limit=limit)
    result["deleted_total"] = sum(result.values())
    return result
