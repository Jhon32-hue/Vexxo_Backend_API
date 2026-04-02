from __future__ import annotations

from django.utils import timezone
from django.db.models import Count

from common.domain_events import EventPriority
from identity.consents.models import ConsentType
from identity.permissions.models import PermissionGrantKind, PermissionSource, PermissionStatus, UserPermissionGrant
from identity.users.domain import UserDomainEventTypes, build_identity_entity_payload
from identity.users.domain.plan_matrix import get_plan_capabilities
from identity.users.services.event_service import publish_user_event_after_commit

GRANT_KIND_PRECEDENCE = {
    PermissionGrantKind.OVERRIDE: 3,
    PermissionGrantKind.MANUAL: 2,
    PermissionGrantKind.ENTITLEMENT: 1,
}

STATUS_PRECEDENCE = {
    PermissionStatus.DENIED: 4,
    PermissionStatus.GRANTED: 3,
    PermissionStatus.REVOKED: 2,
    PermissionStatus.EXPIRED: 1,
}


def _permission_event_type_for_status(status: str) -> str:
    if status == PermissionStatus.DENIED:
        return UserDomainEventTypes.USER_PERMISSION_DENIED
    if status == PermissionStatus.REVOKED:
        return UserDomainEventTypes.USER_PERMISSION_REVOKED
    return UserDomainEventTypes.USER_PERMISSION_GRANTED


def grant_permission(*, user, granted_by, data: dict) -> UserPermissionGrant:
    source = data.get("source", "system")
    requested_status = data.get("status", PermissionStatus.GRANTED)
    default_kind = (
        PermissionGrantKind.OVERRIDE
        if requested_status == PermissionStatus.DENIED
        else (
            PermissionGrantKind.ENTITLEMENT
            if source in {PermissionSource.PLAN, PermissionSource.CONSENT}
            else PermissionGrantKind.MANUAL
        )
    )
    grant, _ = UserPermissionGrant.objects.update_or_create(
        user=user,
        permission_code=data["permission_code"],
        scope_type=data.get("scope_type", "global"),
        scope_id=data.get("scope_id", ""),
        source=source,
        grant_kind=data.get("grant_kind", default_kind),
        defaults={
            "status": requested_status,
            "granted_by": granted_by,
            "expires_at": data.get("expires_at"),
            "metadata": data.get("metadata", {}),
        },
    )
    publish_user_event_after_commit(
        event_type=_permission_event_type_for_status(grant.status),
        payload=build_identity_entity_payload(
            user=user,
            entity_type="permission_grant",
            entity_id=grant.pk,
            extra={
                "permission_code": grant.permission_code,
                "scope_type": grant.scope_type,
                "scope_id": grant.scope_id,
                "status": grant.status,
                "source": grant.source,
                "grant_kind": grant.grant_kind,
            },
        ),
        metadata={"source": "identity.permissions.grant_permission"},
        priority=EventPriority.NORMAL,
    )
    return grant


def revoke_permission(grant: UserPermissionGrant, *, reason: str = "") -> UserPermissionGrant:
    if reason:
        metadata = dict(grant.metadata or {})
        metadata["revoke_reason"] = reason
        grant.metadata = metadata
        grant.save(update_fields=["metadata", "updated_at"])
    grant.revoke(commit=True)
    publish_user_event_after_commit(
        event_type=UserDomainEventTypes.USER_PERMISSION_REVOKED,
        payload=build_identity_entity_payload(
            user=grant.user,
            entity_type="permission_grant",
            entity_id=grant.pk,
            extra={
                "permission_code": grant.permission_code,
                "scope_type": grant.scope_type,
                "scope_id": grant.scope_id,
                "status": grant.status,
                "source": grant.source,
                "grant_kind": grant.grant_kind,
                "reason": reason,
            },
        ),
        metadata={"source": "identity.permissions.revoke_permission"},
        priority=EventPriority.NORMAL,
    )
    return grant


def deny_permission(grant: UserPermissionGrant, *, reason: str = "") -> UserPermissionGrant:
    metadata = dict(grant.metadata or {})
    if reason:
        metadata["deny_reason"] = reason
    metadata["denied_at"] = timezone.now().isoformat()
    grant.metadata = metadata
    grant.deny(commit=False)
    grant.save(update_fields=["status", "revoked_at", "metadata", "updated_at"])
    publish_user_event_after_commit(
        event_type=UserDomainEventTypes.USER_PERMISSION_DENIED,
        payload=build_identity_entity_payload(
            user=grant.user,
            entity_type="permission_grant",
            entity_id=grant.pk,
            extra={
                "permission_code": grant.permission_code,
                "scope_type": grant.scope_type,
                "scope_id": grant.scope_id,
                "status": grant.status,
                "source": grant.source,
                "grant_kind": grant.grant_kind,
                "reason": reason,
            },
        ),
        metadata={"source": "identity.permissions.deny_permission"},
        priority=EventPriority.HIGH,
    )
    return grant


PLAN_PERMISSION_CODES = {
    "accounts.extended.enabled": lambda caps: caps.get("plan") in {"pro", "enterprise"},
    "accounts.multi_primary.enabled": lambda caps: caps.get("max_primary_accounts") is None or (caps.get("max_primary_accounts") or 0) > 1,
    "accounts.connected.extended.enabled": lambda caps: caps.get("max_connected_accounts") is None or (caps.get("max_connected_accounts") or 0) > 1,
    "integrations.multi_connection.enabled": lambda caps: caps.get("max_connected_accounts") is None or (caps.get("max_connected_accounts") or 0) > 1,
    "contacts.extended.enabled": lambda caps: caps.get("max_contacts") is None or (caps.get("max_contacts") or 0) > 10,
    "sharing.extended.enabled": lambda caps: caps.get("max_members_per_account") is None or (caps.get("max_members_per_account") or 0) > 2,
    "reports.extended.enabled": lambda caps: caps.get("max_monthly_reports") is None or (caps.get("max_monthly_reports") or 0) > 1,
    "documents.extended.enabled": lambda caps: caps.get("max_documents_per_month") is None or (caps.get("max_documents_per_month") or 0) > 10,
    "automation.rules.extended.enabled": lambda caps: caps.get("max_rules") is None or (caps.get("max_rules") or 0) > 1,
    "ai.advanced_insights.enabled": lambda caps: str(caps.get("insights_level") or "basic") not in {"basic", ""},
    "alerts.smart.enabled": lambda caps: bool(caps.get("smart_alerts_enabled", False)),
    "payments.embedded.enabled": lambda caps: bool(caps.get("embedded_payments_enabled", False)),
    "payments.payouts.enabled": lambda caps: bool(caps.get("payouts_enabled", False)),
    "product.ads_free.enabled": lambda caps: not bool(caps.get("ads_enabled", True)),
    "product.enterprise_controls.enabled": lambda caps: caps.get("plan") == "enterprise",
}

CONSENT_PERMISSION_CODES = {
    ConsentType.OPEN_BANKING_DATA: ["consents.open_banking_data.enabled"],
    ConsentType.OPEN_BANKING_PAYMENTS: ["consents.open_banking_payments.enabled"],
    ConsentType.DOCUMENT_OCR: ["consents.document_ocr.enabled"],
    ConsentType.AI_PROCESSING: ["consents.ai_processing.enabled"],
    ConsentType.DATA_EXPORT: ["consents.data_export.enabled"],
    ConsentType.MARKETING: ["consents.marketing.enabled"],
}


def _build_consent_scope_id(*, consent_type: str, provider: str = "", scope_code: str = "") -> str:
    return f"{consent_type}:{provider or 'global'}:{scope_code or 'global'}"


def get_effective_permission_resolution(user) -> dict[str, dict]:
    grants = list(
        UserPermissionGrant.objects.filter(user=user)
        .order_by("permission_code", "-updated_at", "-created_at")
    )
    resolutions: dict[str, dict] = {}
    grouped: dict[str, list[UserPermissionGrant]] = {}
    for grant in grants:
        grouped.setdefault(grant.permission_code, []).append(grant)

    for permission_code, rows in grouped.items():
        ordered = sorted(
            rows,
            key=lambda item: (
                GRANT_KIND_PRECEDENCE.get(item.grant_kind, 0),
                STATUS_PRECEDENCE.get(item.status, 0),
                item.updated_at,
                item.created_at,
            ),
            reverse=True,
        )
        selected = ordered[0]
        resolutions[permission_code] = {
            "enabled": selected.status == PermissionStatus.GRANTED,
            "status": selected.status,
            "source": selected.source,
            "grant_kind": selected.grant_kind,
            "scope_type": selected.scope_type,
            "scope_id": selected.scope_id,
            "updated_at": selected.updated_at.isoformat() if selected.updated_at else None,
        }
    return resolutions


def get_effective_permission_codes(user) -> list[str]:
    resolution = get_effective_permission_resolution(user)
    return sorted(
        [
            permission_code
            for permission_code, info in resolution.items()
            if info["enabled"]
        ]
    )


def permission_summary_for_user(user) -> dict:
    base_qs = UserPermissionGrant.objects.filter(user=user)
    status_counts = {
        row["status"]: row["total"]
        for row in base_qs.values("status").annotate(total=Count("id"))
    }
    return {
        "user_id": str(user.pk),
        "total_grants": base_qs.count(),
        "active_grants": status_counts.get(PermissionStatus.GRANTED, 0),
        "denied_grants": status_counts.get(PermissionStatus.DENIED, 0),
        "revoked_grants": status_counts.get(PermissionStatus.REVOKED, 0),
        "expired_grants": status_counts.get(PermissionStatus.EXPIRED, 0),
        "grants_by_source": {
            row["source"]: row["total"]
            for row in base_qs.values("source").annotate(total=Count("id"))
        },
        "grants_by_kind": {
            row["grant_kind"]: row["total"]
            for row in base_qs.values("grant_kind").annotate(total=Count("id"))
        },
        "effective_permission_codes": get_effective_permission_codes(user),
        "effective_permission_resolution": get_effective_permission_resolution(user),
    }


def sync_plan_permissions_for_user(user) -> dict:
    capabilities = get_plan_capabilities(getattr(user, "plan", "free"))
    desired_codes = {
        code
        for code, predicate in PLAN_PERMISSION_CODES.items()
        if predicate(capabilities)
    }
    existing_grants = {
        grant.permission_code: grant
        for grant in UserPermissionGrant.objects.filter(
            user=user,
            source=PermissionSource.PLAN,
            scope_type="global",
        )
    }

    granted_codes: list[str] = []
    revoked_codes: list[str] = []

    for code in sorted(desired_codes):
        grant = existing_grants.get(code)
        if grant is None or grant.status != PermissionStatus.GRANTED:
            grant_permission(
                user=user,
                granted_by=None,
                data={
                    "permission_code": code,
                    "scope_type": "global",
                    "scope_id": "",
                    "status": PermissionStatus.GRANTED,
                    "source": PermissionSource.PLAN,
                    "grant_kind": PermissionGrantKind.ENTITLEMENT,
                    "metadata": {"plan": capabilities["plan"]},
                },
            )
            granted_codes.append(code)

    for code, grant in existing_grants.items():
        if code not in desired_codes and grant.status == PermissionStatus.GRANTED:
            revoke_permission(grant, reason="plan_changed")
            revoked_codes.append(code)

    return {
        "user_id": str(user.pk),
        "plan": capabilities["plan"],
        "granted_codes": granted_codes,
        "revoked_codes": revoked_codes,
    }


def sync_consent_permissions_for_user(*, user, consent_type: str, granted: bool, provider: str = "", scope_code: str = "") -> dict:
    permission_codes = CONSENT_PERMISSION_CODES.get(consent_type, [])
    scope_id = _build_consent_scope_id(consent_type=consent_type, provider=provider, scope_code=scope_code)
    changed_codes: list[str] = []

    for code in permission_codes:
        grant = UserPermissionGrant.objects.filter(
            user=user,
            permission_code=code,
            source=PermissionSource.CONSENT,
            scope_type="consent",
            scope_id=scope_id,
        ).first()
        if granted:
            if grant is None or grant.status != PermissionStatus.GRANTED:
                grant_permission(
                    user=user,
                    granted_by=None,
                    data={
                        "permission_code": code,
                        "scope_type": "consent",
                        "scope_id": scope_id,
                        "status": PermissionStatus.GRANTED,
                        "source": PermissionSource.CONSENT,
                        "grant_kind": PermissionGrantKind.ENTITLEMENT,
                        "metadata": {
                            "consent_type": consent_type,
                            "provider": provider,
                            "scope_code": scope_code,
                        },
                    },
                )
                changed_codes.append(code)
        elif grant is not None and grant.status == PermissionStatus.GRANTED:
            revoke_permission(grant, reason="consent_revoked")
            changed_codes.append(code)

    return {
        "user_id": str(user.pk),
        "consent_type": consent_type,
        "granted": granted,
        "scope_id": scope_id,
        "changed_codes": changed_codes,
    }
