from __future__ import annotations

import json
from datetime import timedelta
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from common.domain_events import EventPriority
from identity.consents.models import ConsentStatus, UserConsent
from identity.users.domain import UserDomainEventTypes, build_identity_entity_payload
from identity.users.services.event_service import publish_user_event_after_commit


def grant_consent(*, user, data: dict) -> UserConsent:
    consent, _ = UserConsent.objects.update_or_create(
        user=user,
        consent_type=data["consent_type"],
        provider=data.get("provider", ""),
        scope_code=data.get("scope_code", ""),
        defaults={
            "external_consent_id": data.get("external_consent_id", ""),
            "purpose": data.get("purpose", ""),
            "legal_basis": data.get("legal_basis", ""),
            "terms_version": data.get("terms_version", ""),
            "privacy_version": data.get("privacy_version", ""),
            "expires_at": data.get("expires_at"),
            "granted_via": data.get("granted_via", ""),
            "data_categories": data.get("data_categories", []),
            "metadata": data.get("metadata", {}),
        },
    )
    consent.grant(commit=True)
    publish_user_event_after_commit(
        event_type=UserDomainEventTypes.USER_CONSENT_GRANTED,
        payload=build_identity_entity_payload(
            user=user,
            entity_type="consent",
            entity_id=consent.pk,
            extra={
                "consent_type": consent.consent_type,
                "provider": consent.provider,
                "scope_code": consent.scope_code,
                "status": consent.status,
            },
        ),
        metadata={"source": "identity.consents.grant_consent"},
        priority=EventPriority.NORMAL,
    )
    return consent


def revoke_consent(consent: UserConsent, *, reason: str = "") -> UserConsent:
    if reason:
        metadata = dict(consent.metadata or {})
        metadata["revoke_reason"] = reason
        consent.metadata = metadata
        consent.save(update_fields=["metadata", "updated_at"])
    consent.revoke(commit=True)
    publish_user_event_after_commit(
        event_type=UserDomainEventTypes.USER_CONSENT_REVOKED,
        payload=build_identity_entity_payload(
            user=consent.user,
            entity_type="consent",
            entity_id=consent.pk,
            extra={
                "consent_type": consent.consent_type,
                "provider": consent.provider,
                "scope_code": consent.scope_code,
                "status": consent.status,
                "reason": reason,
            },
        ),
        metadata={"source": "identity.consents.revoke_consent"},
        priority=EventPriority.HIGH,
    )
    return consent


def consent_summary_for_user(user) -> dict:
    base_qs = UserConsent.objects.filter(user=user)
    now = timezone.now()
    status_counts = {
        row["status"]: row["total"]
        for row in base_qs.values("status").annotate(total=Count("id"))
    }
    active_qs = base_qs.filter(status=ConsentStatus.GRANTED)
    return {
        "user_id": str(user.pk),
        "total_consents": base_qs.count(),
        "granted_consents": status_counts.get(ConsentStatus.GRANTED, 0),
        "revoked_consents": status_counts.get(ConsentStatus.REVOKED, 0),
        "expired_consents": status_counts.get(ConsentStatus.EXPIRED, 0),
        "pending_consents": status_counts.get(ConsentStatus.PENDING, 0),
        "expiring_in_30_days": active_qs.filter(
            expires_at__isnull=False,
            expires_at__gte=now,
            expires_at__lte=now + timedelta(days=30),
        ).count(),
        "active_providers": sorted(
            {
                provider
                for provider in active_qs.exclude(provider="").values_list("provider", flat=True)
            }
        ),
        "consents_by_type": {
            row["consent_type"]: row["total"]
            for row in base_qs.values("consent_type").annotate(total=Count("id"))
        },
    }


def dispatch_consent_revocation_teardown(*, user_id: str | int, provider: str = "", consent_type: str = "", event: dict | None = None) -> dict | None:
    handler_url = str(getattr(settings, "IDENTITY_CONSENT_TEARDOWN_HANDLER_URL", "") or "").strip()
    if handler_url:
        body = json.dumps(
            {
                "event": event or {},
                "user_id": str(user_id),
                "provider": provider or "",
                "consent_type": consent_type or "",
            },
            default=str,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        internal_token = str(getattr(settings, "IDENTITY_CONSENTS_INTERNAL_TOKEN", "") or "").strip()
        if internal_token:
            headers["X-Vexxo-Internal-Token"] = internal_token
        req = Request(url=handler_url, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except URLError as exc:
            if not bool(getattr(settings, "IDENTITY_CONSENT_LOCAL_FALLBACK_ENABLED", True)):
                raise
        except Exception:
            if not bool(getattr(settings, "IDENTITY_CONSENT_LOCAL_FALLBACK_ENABLED", True)):
                raise

    from integrations_stub.banks.services import process_stub_consent_revocation

    return process_stub_consent_revocation(
        user_id=user_id,
        provider=provider,
        consent_type=consent_type,
        event=event,
    )
