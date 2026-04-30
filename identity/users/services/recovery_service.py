"""
Flujos de recovery mobile-first por codigo temporal.
"""

from __future__ import annotations

from django.core.cache import cache
import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from identity.devices.services import trust_device
from identity.users.models import (
    AuthChallengeChannel,
    AuthChallengePurpose,
    AuthChallengeStatus,
    UserAuthChallenge,
)
from identity.sessions.services import complete_session_step_up, revoke_risky_sessions_for_user
from integrations_stub.messaging.services import dispatch_identity_message

logger = logging.getLogger(__name__)
User = get_user_model()


def _normalize_phone(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    prefix = "+" if raw.startswith("+") else ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    return f"{prefix}{digits}" if digits else ""


def _mask_phone(value: str) -> str:
    normalized = _normalize_phone(value)
    if len(normalized) <= 4:
        return normalized
    return f"{normalized[:2]}***{normalized[-2:]}"


def _request_ip(request) -> str | None:
    if request is None:
        return None
    ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR")
    if not ip:
        return None
    return ip.split(",")[0].strip() if "," in ip else ip


def _resolve_code_length(*, purpose: str) -> int:
    if purpose == AuthChallengePurpose.STEP_UP:
        return max(4, int(getattr(settings, "IDENTITY_RECOVERY_CODE_LENGTH", 6) or 6))
    return max(4, int(getattr(settings, "IDENTITY_RECOVERY_CODE_LENGTH", 6) or 6))


def _is_trivial_code(code: str) -> bool:
    if len(set(code)) == 1:
        return True
    ascending = "".join(str((int(code[0]) + idx) % 10) for idx in range(len(code)))
    descending = "".join(str((int(code[0]) - idx) % 10) for idx in range(len(code)))
    return code == ascending or code == descending


def _generate_numeric_code(*, purpose: str) -> str:
    length = _resolve_code_length(purpose=purpose)
    max_value = 10**length
    while True:
        code = str(secrets.randbelow(max_value)).zfill(length)
        if not _is_trivial_code(code):
            return code


def _hash_code(*, challenge_id: int, code: str) -> str:
    raw = f"{settings.SECRET_KEY}:{challenge_id}:{code}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _resolve_active_user_by_phone(phone_number: str):
    normalized = _normalize_phone(phone_number)
    if not normalized:
        return None
    for user in User.objects.filter(is_active=True).exclude(phone_number__isnull=True).exclude(phone_number=""):
        if _normalize_phone(user.phone_number or "") == normalized:
            return user
    return None


def _supersede_pending_challenges(*, user, purpose: str) -> int:
    now = timezone.now()
    challenges = list(
        UserAuthChallenge.objects.filter(
            user=user,
            purpose=purpose,
            status=AuthChallengeStatus.PENDING,
        )
    )
    total = 0
    for challenge in challenges:
        if challenge.expires_at <= now:
            challenge.mark_expired_if_needed()
            continue
        challenge.mark_superseded()
        total += 1
    return total


def _rate_limit_key(scope: str, value: str) -> str:
    normalized = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:24]
    return f"identity:{scope}:{normalized}"


def _hit_rate_limit(*, scope: str, value: str, window_seconds: int, max_requests: int) -> tuple[bool, int]:
    if not value:
        return False, 0
    key = _rate_limit_key(scope, value)
    current = cache.get(key)
    if current is None:
        cache.set(key, 1, timeout=window_seconds)
        return False, 0
    current = int(current) + 1
    cache.set(key, current, timeout=window_seconds)
    if current > max_requests:
        return True, window_seconds
    return False, 0


def _cooldown_remaining(*, scope: str, value: str, cooldown_seconds: int) -> int:
    if not value:
        return 0
    key = _rate_limit_key(f"{scope}:cooldown", value)
    until = cache.get(key)
    now_ts = int(timezone.now().timestamp())
    if until and int(until) > now_ts:
        return int(until) - now_ts
    cache.set(key, now_ts + cooldown_seconds, timeout=max(cooldown_seconds, 1))
    return 0


def _issue_challenge(
    *,
    user,
    purpose: str,
    ttl_seconds: int,
    max_attempts: int,
    request=None,
    metadata: dict | None = None,
):
    _supersede_pending_challenges(user=user, purpose=purpose)
    challenge = UserAuthChallenge.objects.create(
        user=user,
        purpose=purpose,
        channel=AuthChallengeChannel.SMS_CODE,
        delivery_target_masked=_mask_phone(user.phone_number or ""),
        expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
        max_attempts=max_attempts,
        requested_ip=_request_ip(request),
        metadata=metadata or {},
    )
    code = _generate_numeric_code(purpose=purpose)
    challenge.code_hash = _hash_code(challenge_id=challenge.pk, code=code)
    challenge.save(update_fields=["code_hash", "updated_at"])
    return challenge, code


def _dispatch_code(
    *,
    user,
    challenge,
    code: str,
    subject: str,
    event_type: str,
    source: str,
    payload: dict,
    ttl_seconds: int,
):
    message = f"Tu codigo temporal de Vexxo es {code}. Expira en {max(1, ttl_seconds // 60)} minuto(s)."
    return dispatch_identity_message(
        owner=user,
        subject=subject,
        message=message,
        event_type=event_type,
        source=source,
        payload=payload,
        debug_code=code,
    )


def _resolve_generic_recovery_response(*, retry_after_seconds: int = 0) -> dict:
    response = {
        "detail": "Si el telefono corresponde a un usuario activo, enviaremos un codigo temporal.",
        "ttl_seconds": int(getattr(settings, "IDENTITY_RECOVERY_CODE_TTL_SECONDS", 120) or 120),
    }
    if retry_after_seconds > 0:
        response["retry_after_seconds"] = retry_after_seconds
    return response


def request_password_recovery_code(*, phone_number: str, request=None) -> dict:
    normalized_phone = _normalize_phone(phone_number)
    request_ip = _request_ip(request) or ""
    cooldown_seconds = int(getattr(settings, "IDENTITY_RECOVERY_COOLDOWN_SECONDS", 45) or 45)
    rate_window_seconds = int(getattr(settings, "IDENTITY_RECOVERY_RATE_WINDOW_SECONDS", 600) or 600)
    max_requests_per_window = int(getattr(settings, "IDENTITY_RECOVERY_MAX_REQUESTS_PER_WINDOW", 5) or 5)

    for scope_value in [normalized_phone, request_ip]:
        blocked, retry_after = _hit_rate_limit(
            scope="password_recovery",
            value=scope_value,
            window_seconds=rate_window_seconds,
            max_requests=max_requests_per_window,
        )
        if blocked:
            return _resolve_generic_recovery_response(retry_after_seconds=retry_after)
        retry_after = _cooldown_remaining(
            scope="password_recovery",
            value=scope_value,
            cooldown_seconds=cooldown_seconds,
        )
        if retry_after > 0:
            return _resolve_generic_recovery_response(retry_after_seconds=retry_after)

    user = _resolve_active_user_by_phone(phone_number)
    generic_response = _resolve_generic_recovery_response()
    if user is None:
        return generic_response

    ttl_seconds = int(getattr(settings, "IDENTITY_RECOVERY_CODE_TTL_SECONDS", 120) or 120)
    max_attempts = int(getattr(settings, "IDENTITY_RECOVERY_MAX_ATTEMPTS", 5) or 5)
    challenge, code = _issue_challenge(
        user=user,
        purpose=AuthChallengePurpose.PASSWORD_RECOVERY,
        ttl_seconds=ttl_seconds,
        max_attempts=max_attempts,
        request=request,
        metadata={"transport": "sms_stub"},
    )

    payload = {
        "challenge_id": str(challenge.pk),
        "delivery_target_masked": challenge.delivery_target_masked,
        "purpose": challenge.purpose,
        "expires_at": challenge.expires_at.isoformat(),
    }
    delivery = _dispatch_code(
        user=user,
        challenge=challenge,
        code=code,
        subject="Codigo temporal de recuperacion",
        event_type="users.password_recovery.code_requested.v1",
        source="identity.users.recovery_service",
        payload=payload,
        ttl_seconds=ttl_seconds,
    )
    if str(delivery.status) == "failed":
        challenge.mark_failed_dispatch(error=str((delivery.payload or {}).get("dispatch_error") or ""))

    logger.info(
        "[users.recovery] challenge=%s owner=%s phone=%s transport=%s",
        challenge.pk,
        user.pk,
        challenge.delivery_target_masked,
        str((delivery.payload or {}).get("transport") or ""),
    )
    return generic_response


def confirm_password_recovery_code(*, phone_number: str, code: str):
    user = _resolve_active_user_by_phone(phone_number)
    if user is None:
        return None, "invalid_or_expired"

    challenge = (
        UserAuthChallenge.objects.filter(
            user=user,
            purpose=AuthChallengePurpose.PASSWORD_RECOVERY,
            channel=AuthChallengeChannel.SMS_CODE,
            status=AuthChallengeStatus.PENDING,
        )
        .order_by("-created_at")
        .first()
    )
    if challenge is None:
        return None, "invalid_or_expired"

    challenge.mark_expired_if_needed()
    if not challenge.can_verify():
        return None, "invalid_or_expired"

    hashed = _hash_code(challenge_id=challenge.pk, code=str(code or "").strip())
    if not secrets.compare_digest(challenge.code_hash, hashed):
        challenge.register_failed_attempt()
        return None, "invalid_or_expired"

    challenge.mark_consumed()
    return user, "", challenge


def _resolve_pending_step_up_challenge(*, user, session_id=None):
    qs = UserAuthChallenge.objects.filter(
        user=user,
        purpose=AuthChallengePurpose.STEP_UP,
        channel=AuthChallengeChannel.SMS_CODE,
        status=AuthChallengeStatus.PENDING,
    )
    if session_id:
        qs = qs.filter(metadata__session_id=str(session_id))
    return qs.order_by("-created_at").first()


def request_step_up_code(*, user, session, request=None) -> dict:
    if not session.requires_step_up:
        return {"detail": "La sesion no requiere step-up.", "requires_step_up": False}
    if not _normalize_phone(user.phone_number or ""):
        return {
            "detail": "El usuario no tiene telefono disponible para step-up embebido.",
            "requires_step_up": True,
            "delivery_available": False,
        }

    ttl_seconds = int(getattr(settings, "IDENTITY_STEP_UP_CODE_TTL_SECONDS", 180) or 180)
    max_attempts = int(getattr(settings, "IDENTITY_STEP_UP_MAX_ATTEMPTS", 5) or 5)
    challenge, code = _issue_challenge(
        user=user,
        purpose=AuthChallengePurpose.STEP_UP,
        ttl_seconds=ttl_seconds,
        max_attempts=max_attempts,
        request=request,
        metadata={
            "transport": "sms_stub",
            "session_id": str(session.pk),
            "session_risk_level": session.risk_level,
        },
    )
    payload = {
        "challenge_id": str(challenge.pk),
        "delivery_target_masked": challenge.delivery_target_masked,
        "purpose": challenge.purpose,
        "expires_at": challenge.expires_at.isoformat(),
        "session_id": str(session.pk),
    }
    delivery = _dispatch_code(
        user=user,
        challenge=challenge,
        code=code,
        subject="Codigo temporal de verificacion",
        event_type="users.step_up.code_requested.v1",
        source="identity.users.recovery_service",
        payload=payload,
        ttl_seconds=ttl_seconds,
    )
    if str(delivery.status) == "failed":
        challenge.mark_failed_dispatch(error=str((delivery.payload or {}).get("dispatch_error") or ""))
    return {
        "detail": "Se envio un codigo temporal para completar step-up.",
        "requires_step_up": True,
        "delivery_available": True,
        "session_id": session.pk,
        "delivery_target_masked": challenge.delivery_target_masked,
        "ttl_seconds": ttl_seconds,
    }


def confirm_step_up_code(*, user, session, code: str):
    challenge = _resolve_pending_step_up_challenge(user=user, session_id=session.pk)
    if challenge is None:
        return False, "invalid_or_expired", None

    challenge.mark_expired_if_needed()
    if not challenge.can_verify():
        return False, "invalid_or_expired", None

    hashed = _hash_code(challenge_id=challenge.pk, code=str(code or "").strip())
    if not secrets.compare_digest(challenge.code_hash, hashed):
        challenge.register_failed_attempt()
        return False, "invalid_or_expired", None

    challenge.mark_consumed()
    complete_session_step_up(session=session, challenge_id=challenge.pk)
    if session.device_id and bool(getattr(settings, "IDENTITY_STEP_UP_TRUST_DEVICE_ON_SUCCESS", True)):
        trust_device(session.device)
    revoked = 0
    if bool(getattr(settings, "IDENTITY_STEP_UP_REVOKE_OTHER_RISKY_SESSIONS", True)):
        revoked = revoke_risky_sessions_for_user(
            user=user,
            exclude_session_id=session.pk,
            reason="step_up_completed_cleanup",
        )
    return True, "", {"challenge_id": challenge.pk, "revoked_risky_sessions": revoked}
