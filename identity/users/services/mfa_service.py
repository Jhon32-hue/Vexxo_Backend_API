from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from integrations.credentials.services import reveal_credential, revoke_credential, store_credential
from identity.devices.services import trust_device
from identity.sessions.services import complete_session_step_up, revoke_risky_sessions_for_user
from identity.users.models import UserMfaMethod


def _totp_code(secret: str, counter: int, digits: int = 6) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def _recovery_hash(code: str) -> str:
    key = str(getattr(settings, "MFA_RECOVERY_HASH_KEY", "") or settings.SECRET_KEY).encode("utf-8")
    normalized = str(code or "").replace("-", "").strip().upper().encode("ascii")
    return hmac.new(key, normalized, hashlib.sha256).hexdigest()


def _new_recovery_codes(total: int = 8) -> list[str]:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ["-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3)) for _ in range(total)]


def get_active_mfa_method(user) -> UserMfaMethod | None:
    return user.mfa_methods.select_related("secret_credential").filter(status=UserMfaMethod.Status.ACTIVE).first()


@transaction.atomic
def begin_totp_enrollment(*, user, current_password: str) -> tuple[UserMfaMethod, str, str]:
    if not user.check_password(current_password):
        raise ValueError("invalid_password")
    previous = list(user.mfa_methods.select_for_update().filter(method=UserMfaMethod.Method.TOTP))
    for method in previous:
        if method.secret_credential_id and method.secret_credential.status == "active":
            revoke_credential(method.secret_credential)
        method.status = UserMfaMethod.Status.DISABLED
        method.disabled_at = timezone.now()
        method.save(update_fields=["status", "disabled_at", "updated_at"])

    method = UserMfaMethod.objects.create(user=user, method=UserMfaMethod.Method.TOTP)
    secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    credential = store_credential(
        owner=user,
        provider="vexxo_identity",
        credential_type="mfa_totp_seed",
        secret=secret,
        external_reference=str(method.public_id),
        safe_metadata={"purpose": "mfa_totp"},
    )
    method.secret_credential = credential
    method.save(update_fields=["secret_credential", "updated_at"])
    issuer = str(getattr(settings, "MFA_TOTP_ISSUER", "Vexxo") or "Vexxo")
    label = f"{issuer}:{user.email}"
    uri = f"otpauth://totp/{quote(label)}?{urlencode({'secret': secret, 'issuer': issuer, 'algorithm': 'SHA1', 'digits': 6, 'period': 30})}"
    return method, secret, uri


def _verify_totp(method: UserMfaMethod, code: str, *, consume: bool) -> bool:
    if not method.secret_credential_id:
        return False
    secret = reveal_credential(method.secret_credential)
    current_counter = int(time.time()) // 30
    normalized = str(code or "").strip()
    for counter in range(current_counter - 1, current_counter + 2):
        if method.last_totp_counter is not None and counter <= method.last_totp_counter:
            continue
        if secrets.compare_digest(_totp_code(secret, counter), normalized):
            if consume:
                method.last_totp_counter = counter
                method.last_used_at = timezone.now()
                method.save(update_fields=["last_totp_counter", "last_used_at", "updated_at"])
            return True
    return False


@transaction.atomic
def confirm_totp_enrollment(*, user, code: str) -> tuple[UserMfaMethod, list[str]]:
    method = user.mfa_methods.select_for_update().filter(
        method=UserMfaMethod.Method.TOTP,
        status=UserMfaMethod.Status.PENDING,
    ).first()
    if method is None or not _verify_totp(method, code, consume=True):
        raise ValueError("invalid_totp")
    recovery_codes = _new_recovery_codes()
    method.recovery_code_hashes = [_recovery_hash(item) for item in recovery_codes]
    method.status = UserMfaMethod.Status.ACTIVE
    method.confirmed_at = timezone.now()
    method.save(update_fields=["recovery_code_hashes", "status", "confirmed_at", "updated_at"])
    return method, recovery_codes


@transaction.atomic
def verify_mfa_code(*, user, code: str) -> tuple[bool, str]:
    method = get_active_mfa_method(user)
    if method is None:
        return False, "mfa_not_configured"
    if _verify_totp(method, code, consume=True):
        return True, "totp"
    candidate = _recovery_hash(code)
    hashes = list(method.recovery_code_hashes or [])
    for index, stored in enumerate(hashes):
        if secrets.compare_digest(candidate, str(stored)):
            hashes.pop(index)
            method.recovery_code_hashes = hashes
            method.last_used_at = timezone.now()
            method.save(update_fields=["recovery_code_hashes", "last_used_at", "updated_at"])
            return True, "recovery_code"
    return False, "invalid_code"


@transaction.atomic
def disable_mfa(*, user, current_password: str) -> None:
    if not user.check_password(current_password):
        raise ValueError("invalid_password")
    method = get_active_mfa_method(user)
    if method is None:
        return
    if method.secret_credential_id:
        revoke_credential(method.secret_credential)
    method.status = UserMfaMethod.Status.DISABLED
    method.disabled_at = timezone.now()
    method.recovery_code_hashes = []
    method.save(update_fields=["status", "disabled_at", "recovery_code_hashes", "updated_at"])


def verify_mfa_step_up(*, user, session, code: str) -> tuple[bool, str, int]:
    verified, method = verify_mfa_code(user=user, code=code)
    if not verified:
        return False, method, 0
    complete_session_step_up(session=session)
    if session.device_id and bool(getattr(settings, "IDENTITY_STEP_UP_TRUST_DEVICE_ON_SUCCESS", True)):
        trust_device(session.device)
    revoked = 0
    if bool(getattr(settings, "IDENTITY_STEP_UP_REVOKE_OTHER_RISKY_SESSIONS", True)):
        revoked = revoke_risky_sessions_for_user(
            user=user,
            exclude_session_id=session.pk,
            reason="mfa_step_up_completed_cleanup",
        )
    return True, method, revoked
