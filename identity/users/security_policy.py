from __future__ import annotations

from dataclasses import dataclass

from rest_framework.exceptions import PermissionDenied


@dataclass(frozen=True)
class SensitiveOperationPolicy:
    assurance: str
    reason: str


SENSITIVE_OPERATION_POLICIES = {
    "identity.password.change": SensitiveOperationPolicy("clear_session_and_revoke_all", "Password changes invalidate every active token family."),
    "identity.mfa.enroll": SensitiveOperationPolicy("clear_session_and_current_password", "MFA enrollment changes the account assurance boundary."),
    "identity.mfa.disable": SensitiveOperationPolicy("clear_session_and_current_password", "MFA removal requires password reauthentication."),
    "identity.device.trust": SensitiveOperationPolicy("clear_session", "A risky session cannot trust another device."),
    "identity.social.unlink": SensitiveOperationPolicy("clear_session", "Unlinking an identity changes recovery options."),
    "identity.device.attest": SensitiveOperationPolicy("platform_challenge", "The official platform challenge is the assurance mechanism."),
    "identity.admin.suspend": SensitiveOperationPolicy("staff_and_reason", "Suspension invalidates all sessions immediately."),
}


def enforce_operation_policy(request, operation: str) -> None:
    if operation not in SENSITIVE_OPERATION_POLICIES:
        raise RuntimeError(f"Undefined sensitive operation policy: {operation}")
    session = getattr(request, "vexxo_session", None)
    # SessionAuthentication/force_authenticate do not carry a JWT session and
    # remain usable for admin and test surfaces protected by their own auth.
    if session is not None and session.requires_step_up:
        raise PermissionDenied(
            detail={"code": "step_up_required", "operation": operation, "detail": "Completa step-up antes de esta operacion."}
        )
