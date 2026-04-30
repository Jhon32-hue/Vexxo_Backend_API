from __future__ import annotations

import logging

from django.conf import settings

from tasks.async_backends import CloudTaskDispatchConfig, cloud_tasks_ready, dispatch_job

logger = logging.getLogger(__name__)

JOB_TYPE = "identity.consents"


def consent_teardown_cloud_tasks_ready() -> bool:
    return cloud_tasks_ready(_cloud_task_config(user_id="", provider="", consent_type="", event=None))


def _event_as_dict(event) -> dict:
    if event is None:
        return {"type": "users.consent.revoked.v1", "context": "identity"}
    if hasattr(event, "to_dict"):
        return event.to_dict()
    return {
        "type": getattr(event, "type", "users.consent.revoked.v1"),
        "context": getattr(getattr(event, "context", None), "value", "identity"),
        "correlation_id": getattr(event, "correlation_id", None),
        "causation_id": getattr(event, "id", None),
    }


def _cloud_task_config(*, user_id: str | int, provider: str = "", consent_type: str = "", event=None) -> CloudTaskDispatchConfig:
    safe_suffix = f"{user_id}-{provider or 'all'}-{consent_type or 'consent'}".replace("/", "-").replace(":", "-")
    return CloudTaskDispatchConfig(
        job_type=JOB_TYPE,
        enabled=bool(getattr(settings, "IDENTITY_CONSENT_CLOUD_TASKS_ENABLED", False)),
        queue=str(getattr(settings, "IDENTITY_CONSENT_CLOUD_TASKS_QUEUE", "") or ""),
        location=str(getattr(settings, "IDENTITY_CONSENT_CLOUD_TASKS_LOCATION", "") or ""),
        handler_url=str(getattr(settings, "IDENTITY_CONSENT_TEARDOWN_HANDLER_URL", "") or ""),
        payload={
            "event": _event_as_dict(event),
            "user_id": str(user_id or ""),
            "provider": str(provider or ""),
            "consent_type": str(consent_type or ""),
        },
        task_name=f"identity-consent-{safe_suffix}" if user_id else "",
        internal_token=str(getattr(settings, "IDENTITY_CONSENTS_INTERNAL_TOKEN", "") or ""),
        service_account_email=str(getattr(settings, "IDENTITY_CONSENT_TASK_SERVICE_ACCOUNT_EMAIL", "") or ""),
        audience=str(getattr(settings, "IDENTITY_CONSENT_TASK_AUDIENCE", "") or ""),
        buffer_seconds=max(0, int(getattr(settings, "IDENTITY_CONSENT_TASK_BUFFER_SECONDS", 0) or 0)),
        headers={
            "X-Vexxo-Event-Type": "users.consent.revoked.v1",
            "X-Vexxo-Context": "identity",
        },
    )


def _process_inline_for_tests(*, user_id: str | int, provider: str = "", consent_type: str = "", event=None) -> dict:
    from integrations_stub.banks.services import process_stub_consent_revocation

    return process_stub_consent_revocation(
        user_id=user_id,
        provider=provider,
        consent_type=consent_type,
        event=_event_as_dict(event),
    )


def dispatch_consent_revocation_teardown(
    *,
    user_id: str | int,
    provider: str = "",
    consent_type: str = "",
    event: dict | None = None,
) -> dict:
    if not user_id:
        return {"result": "missing_user_id"}

    result = dispatch_job(
        job_type=JOB_TYPE,
        cloud_task_config=_cloud_task_config(
            user_id=user_id,
            provider=provider,
            consent_type=consent_type,
            event=event,
        ),
        local_worker_available=False,
        inline_handler=lambda: _process_inline_for_tests(
            user_id=user_id,
            provider=provider,
            consent_type=consent_type,
            event=event,
        ),
    )
    if result.get("result") == "inline_handler_failed":
        logger.exception(
            "[identity.consents] inline teardown failed user_id=%s provider=%s consent_type=%s",
            user_id,
            provider or "*",
            consent_type or "*",
        )
        return {
            "result": "pipeline_unavailable",
            "dispatch_backend": result.get("dispatch_backend", ""),
            "error": result.get("error", ""),
        }
    if result.get("result") == "inline_processed":
        inline_result = dict(result.get("inline_result") or {})
        inline_result["result"] = "inline_processed"
        inline_result["dispatch_backend"] = result.get("dispatch_backend", "")
        return inline_result
    return result
