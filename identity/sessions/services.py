from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from common.domain_events import EventPriority
from identity.devices.models import DeviceTrustLevel, UserDevice
from identity.sessions.models import SessionRiskLevel, SessionStatus, SessionType, UserSession
from identity.users.domain import UserDomainEventTypes, build_identity_entity_payload
from identity.users.services.event_service import publish_user_event_after_commit


def _request_ip(request) -> str | None:
    if not request:
        return None
    ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR")
    if not ip:
        return None
    return ip.split(",")[0].strip() if "," in ip else ip


def _resolve_session_risk(*, device: UserDevice | None) -> tuple[str, bool]:
    if device is None:
        return SessionRiskLevel.MEDIUM, bool(getattr(settings, "IDENTITY_STEP_UP_ON_UNKNOWN_DEVICE", True))
    if device.trust_level == DeviceTrustLevel.TRUSTED:
        return SessionRiskLevel.LOW, False
    if device.trust_level == DeviceTrustLevel.SUSPICIOUS:
        return SessionRiskLevel.HIGH, bool(getattr(settings, "IDENTITY_STEP_UP_ON_SUSPICIOUS_DEVICE", True))
    if device.trust_level == DeviceTrustLevel.BLOCKED:
        return SessionRiskLevel.CRITICAL, True
    return SessionRiskLevel.MEDIUM, bool(getattr(settings, "IDENTITY_STEP_UP_ON_UNKNOWN_DEVICE", True))


def register_user_session(
    *,
    user,
    request=None,
    session_key: str | None = None,
    refresh_jti: str = "",
    access_jti: str = "",
    session_type: str = SessionType.PASSWORD,
    provider: str = "",
    device: UserDevice | None = None,
    expires_at=None,
    family_id: str = "",
    correlation_id: str = "",
    metadata: dict | None = None,
) -> UserSession:
    risk_level, requires_step_up = _resolve_session_risk(device=device)
    family_value = family_id or str(uuid.uuid4())
    session = UserSession.objects.create(
        user=user,
        device=device,
        family_id=family_value,
        session_key=session_key or str(uuid.uuid4()),
        refresh_jti=refresh_jti or "",
        access_jti=access_jti or "",
        session_type=session_type,
        provider=provider,
        risk_level=risk_level,
        requires_step_up=requires_step_up,
        ip_address=_request_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
        expires_at=expires_at,
        correlation_id=correlation_id,
        metadata=metadata or {},
    )
    publish_user_event_after_commit(
        event_type=UserDomainEventTypes.USER_SESSION_STARTED,
        payload=build_identity_entity_payload(
            user=user,
            entity_type="session",
            entity_id=session.pk,
            extra={
                "session_key": session.session_key,
                "family_id": session.family_id,
                "session_type": session.session_type,
                "provider": session.provider,
                "device_id": str(device.pk) if device else None,
                "risk_level": session.risk_level,
                "requires_step_up": session.requires_step_up,
            },
        ),
        metadata={"source": "identity.sessions.register_user_session"},
        priority=EventPriority.NORMAL,
        correlation_id=correlation_id or None,
    )
    _enforce_active_session_limit(user)
    return session


def revoke_user_session(session: UserSession, *, reason: str = "") -> UserSession:
    session.revoke(reason=reason, commit=True)
    publish_user_event_after_commit(
        event_type=UserDomainEventTypes.USER_SESSION_REVOKED,
        payload=build_identity_entity_payload(
            user=session.user,
            entity_type="session",
            entity_id=session.pk,
            extra={"reason": reason, "session_key": session.session_key},
        ),
        metadata={"source": "identity.sessions.revoke_user_session"},
        priority=EventPriority.NORMAL,
        correlation_id=session.correlation_id or None,
    )
    return session


def revoke_session_by_refresh_token(*, refresh_jti: str, reason: str = "logout") -> UserSession | None:
    if not refresh_jti:
        return None
    session = UserSession.objects.filter(refresh_jti=refresh_jti).first()
    if session is None:
        return None
    return revoke_user_session(session, reason=reason)


def get_active_session_by_refresh_jti(*, refresh_jti: str) -> UserSession | None:
    if not refresh_jti:
        return None
    return UserSession.objects.filter(refresh_jti=refresh_jti, status=SessionStatus.ACTIVE).first()


def get_active_session_by_access_jti(*, access_jti: str) -> UserSession | None:
    if not access_jti:
        return None
    return UserSession.objects.filter(access_jti=access_jti, status=SessionStatus.ACTIVE).first()


def detect_refresh_reuse(*, refresh_jti: str) -> UserSession | None:
    if not refresh_jti:
        return None
    return UserSession.objects.filter(
        previous_refresh_jti=refresh_jti,
        status=SessionStatus.ACTIVE,
    ).first()


def rotate_session_refresh(*, session: UserSession, refresh_jti: str, access_jti: str = "") -> UserSession:
    session.rotate_refresh(new_refresh_jti=refresh_jti, new_access_jti=access_jti, commit=True)
    return session


def touch_session(session: UserSession) -> UserSession:
    session.touch(commit=True)
    return session


def revoke_all_active_sessions_for_user(user, *, reason: str = "security_event") -> int:
    sessions = list(UserSession.objects.filter(user=user, status=SessionStatus.ACTIVE))
    for session in sessions:
        revoke_user_session(session, reason=reason)
    return len(sessions)


def revoke_session_family(*, family_id: str, reason: str = "session_family_revoked") -> int:
    if not family_id:
        return 0
    sessions = list(UserSession.objects.filter(family_id=family_id, status=SessionStatus.ACTIVE))
    for session in sessions:
        revoke_user_session(session, reason=reason)
    return len(sessions)


def revoke_device_sessions(*, device_id, reason: str = "device_revoked") -> int:
    sessions = list(UserSession.objects.filter(device_id=device_id, status=SessionStatus.ACTIVE))
    for session in sessions:
        revoke_user_session(session, reason=reason)
    return len(sessions)


def revoke_provider_sessions_for_user(*, user, provider: str, reason: str = "provider_unlinked") -> int:
    provider = str(provider or "").strip().lower()
    if not provider:
        return 0
    sessions = list(
        UserSession.objects.filter(
            user=user,
            status=SessionStatus.ACTIVE,
            provider__iexact=provider,
        )
    )
    for session in sessions:
        revoke_user_session(session, reason=reason)
    return len(sessions)


def revoke_risky_sessions_for_user(*, user, exclude_session_id=None, reason: str = "risk_cleanup") -> int:
    sessions = list(
        UserSession.objects.filter(
            user=user,
            status=SessionStatus.ACTIVE,
            requires_step_up=True,
        ).exclude(pk=exclude_session_id)
    )
    for session in sessions:
        revoke_user_session(session, reason=reason)
    return len(sessions)


def complete_session_step_up(*, session: UserSession, challenge_id=None) -> UserSession:
    metadata = dict(session.metadata or {})
    metadata["step_up_completed"] = True
    if challenge_id is not None:
        metadata["step_up_challenge_id"] = str(challenge_id)
    metadata["step_up_completed_at"] = timezone.now().isoformat()
    session.requires_step_up = False
    session.metadata = metadata
    session.save(update_fields=["requires_step_up", "metadata", "updated_at"])
    return session


def _enforce_active_session_limit(user) -> None:
    limit = int(getattr(settings, "IDENTITY_MAX_ACTIVE_SESSIONS", 5) or 0)
    if limit <= 0:
        return
    sessions = list(
        UserSession.objects.filter(user=user, status=SessionStatus.ACTIVE).order_by("-authenticated_at", "-created_at")
    )
    overflow = sessions[limit:]
    for session in overflow:
        revoke_user_session(session, reason="session_limit_exceeded")


def session_summary_for_user(user) -> dict:
    base_qs = UserSession.objects.filter(user=user)
    now = timezone.now()
    status_counts = {
        row["status"]: row["total"]
        for row in base_qs.values("status").annotate(total=Count("id"))
    }
    return {
        "user_id": str(user.pk),
        "total_sessions": base_qs.count(),
        "active_sessions": status_counts.get(SessionStatus.ACTIVE, 0),
        "revoked_sessions": status_counts.get(SessionStatus.REVOKED, 0),
        "expired_sessions": status_counts.get(SessionStatus.EXPIRED, 0),
        "failed_sessions": status_counts.get(SessionStatus.FAILED, 0),
        "stale_active_sessions": base_qs.filter(
            status=SessionStatus.ACTIVE,
            last_seen_at__lt=now - timedelta(days=30),
        ).count(),
        "active_families": base_qs.filter(status=SessionStatus.ACTIVE).exclude(family_id="").values("family_id").distinct().count(),
        "high_risk_active_sessions": base_qs.filter(
            status=SessionStatus.ACTIVE,
            risk_level__in=[SessionRiskLevel.HIGH, SessionRiskLevel.CRITICAL],
        ).count(),
        "step_up_pending_sessions": base_qs.filter(status=SessionStatus.ACTIVE, requires_step_up=True).count(),
        "sessions_by_provider": {
            row["provider"] or "direct": row["total"]
            for row in base_qs.values("provider").annotate(total=Count("id"))
        },
        "sessions_by_type": {
            row["session_type"]: row["total"]
            for row in base_qs.values("session_type").annotate(total=Count("id"))
        },
        "sessions_by_risk": {
            row["risk_level"]: row["total"]
            for row in base_qs.values("risk_level").annotate(total=Count("id"))
        },
    }
