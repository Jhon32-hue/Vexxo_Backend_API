"""
Casos de uso de sincronizacion externa para `Account`.

Descripcion general:
- centraliza el ciclo de vida de vinculacion y estado de sync de cuentas
  conectadas a proveedores externos

Analisis detallado:
- combina mutacion del agregado con emision de eventos de sync y lifecycle
- permite que el viewset solo orqueste permisos, validacion y auditoria
- endurece idempotencia operativa para integraciones y workers
- mantiene una maquina de estados monotona por corrida usando `sync_run_id`
  persistido en `Account.sync_runtime`
"""

from __future__ import annotations

import hashlib
import json
import uuid

from django.utils import timezone

from finance.accounts.domain.events import (
    AccountDomainEventTypes,
    build_account_lifecycle_payload,
    build_account_sync_payload,
)
from finance.accounts.models import SyncStatus
from finance.accounts.services.outbox_service import (
    publish_account_event,
    publish_account_lifecycle_event,
    publish_account_sync_event,
)

SYNC_DEDUPE_WINDOW_SECONDS = 300
SYNC_RUNTIME_VERSION = 1
SYNC_TERMINAL_ACTIONS = {"success", "error", "stale"}


def _merge_sync_metadata(metadata: dict | None = None, *, source: str) -> dict:
    merged = {"source": source}
    merged.update(metadata or {})
    return merged


def _normalize_sync_run_id(value) -> str:
    return str(value or "").strip()[:64]


def _sync_command_key(*, account, action: str, data: dict, metadata: dict | None = None) -> str:
    raw = json.dumps(
        {
            "action": action,
            "account_id": account.pk,
            "provider": account.provider,
            "external_id": account.external_id,
            "sync_run_id": _normalize_sync_run_id(data.get("sync_run_id") or (metadata or {}).get("sync_run_id")),
            "sync_cursor": data.get("sync_cursor", account.sync_cursor),
            "next_sync_at": str(data.get("next_sync_at", account.next_sync_at) or ""),
            "run_at": str(data.get("run_at") or ""),
            "delay_minutes": data.get("delay_minutes"),
            "message": str(data.get("message", "") or ""),
            "metadata": metadata or {},
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sync_runtime(account) -> dict:
    return dict(getattr(account, "sync_runtime", None) or {})


def _set_sync_runtime(account, runtime: dict) -> None:
    normalized = dict(runtime or {})
    normalized["version"] = SYNC_RUNTIME_VERSION
    account.sync_runtime = normalized


def _sync_trace(account) -> dict:
    provider_metadata = dict(account.provider_metadata or {})
    return dict(provider_metadata.get("_vexxo_sync_trace") or {})


def _record_sync_trace(*, account, action: str, command_key: str, metadata: dict | None, result: str):
    provider_metadata = dict(account.provider_metadata or {})
    provider_metadata["_vexxo_sync_trace"] = {
        "action": action,
        "command_key": command_key,
        "result": result,
        "at": timezone.now().isoformat(),
        "request_id": str((metadata or {}).get("request_id") or ""),
        "correlation_id": str((metadata or {}).get("correlation_id") or ""),
        "causation_id": str((metadata or {}).get("causation_id") or ""),
        "sync_run_id": _normalize_sync_run_id((metadata or {}).get("sync_run_id")),
    }
    account.provider_metadata = provider_metadata


def _resolve_sync_run_id(*, account, action: str, data: dict, metadata: dict | None, command_key: str) -> str:
    runtime = _sync_runtime(account)
    explicit = _normalize_sync_run_id(data.get("sync_run_id") or (metadata or {}).get("sync_run_id"))
    if explicit:
        return explicit

    current_run_id = _normalize_sync_run_id(runtime.get("current_run_id"))
    if current_run_id:
        return current_run_id

    if action in {"schedule", "running"}:
        return command_key[:32] or uuid.uuid4().hex

    if account.sync_status == SyncStatus.RUNNING:
        return command_key[:32] or uuid.uuid4().hex

    return ""


def _bootstrap_legacy_running_runtime(*, account, sync_run_id: str, command_key: str) -> dict:
    runtime = _sync_runtime(account)
    if runtime:
        return runtime

    now = timezone.now().isoformat()
    runtime.update(
        {
            "version": SYNC_RUNTIME_VERSION,
            "current_run_id": sync_run_id,
            "current_phase": "running",
            "started_at": now,
            "last_transition_at": now,
            "last_command_key": command_key,
            "last_transition_result": "bootstrapped_legacy_running",
        }
    )
    return runtime


def _advance_sync_runtime(*, account, action: str, sync_run_id: str, command_key: str) -> tuple[bool, str, dict]:
    runtime = _sync_runtime(account)
    now = timezone.now().isoformat()
    current_run_id = _normalize_sync_run_id(runtime.get("current_run_id"))
    current_phase = str(runtime.get("current_phase") or "")
    last_terminal_run_id = _normalize_sync_run_id(runtime.get("last_terminal_run_id"))
    last_terminal_phase = str(runtime.get("last_terminal_phase") or "")

    if action == "schedule":
        if current_run_id and current_run_id != sync_run_id and current_phase in {"scheduled", "running"}:
            runtime["last_transition_result"] = "ignored_concurrent_schedule"
            return False, "ignored_concurrent_schedule", runtime
        if current_run_id == sync_run_id and current_phase == "scheduled":
            runtime["last_transition_result"] = "duplicate_schedule"
            return False, "duplicate_schedule", runtime
        runtime.update(
            {
                "version": SYNC_RUNTIME_VERSION,
                "current_run_id": sync_run_id,
                "current_phase": "scheduled",
                "scheduled_at": now,
                "last_transition_at": now,
                "last_command_key": command_key,
                "last_transition_result": "scheduled",
            }
        )
        return True, "scheduled", runtime

    if action == "running":
        if current_run_id and current_run_id != sync_run_id and current_phase in {"scheduled", "running"}:
            runtime["last_transition_result"] = "ignored_concurrent_run"
            return False, "ignored_concurrent_run", runtime
        if current_run_id == sync_run_id and current_phase == "running":
            runtime["last_transition_result"] = "duplicate_running"
            return False, "duplicate_running", runtime
        runtime.update(
            {
                "version": SYNC_RUNTIME_VERSION,
                "current_run_id": sync_run_id,
                "current_phase": "running",
                "started_at": runtime.get("started_at") or now,
                "last_transition_at": now,
                "last_command_key": command_key,
                "last_transition_result": "running",
            }
        )
        return True, "running", runtime

    if action in SYNC_TERMINAL_ACTIONS and not current_run_id and account.sync_status == SyncStatus.RUNNING and sync_run_id:
        runtime = _bootstrap_legacy_running_runtime(account=account, sync_run_id=sync_run_id, command_key=command_key)
        current_run_id = _normalize_sync_run_id(runtime.get("current_run_id"))
        current_phase = str(runtime.get("current_phase") or "")

    if action in SYNC_TERMINAL_ACTIONS:
        if sync_run_id and last_terminal_run_id == sync_run_id:
            runtime["last_transition_result"] = "already_terminal"
            return False, "already_terminal", runtime
        if not current_run_id:
            runtime["last_transition_result"] = "no_active_run"
            return False, "no_active_run", runtime
        if current_run_id != sync_run_id:
            runtime["last_transition_result"] = "stale_run"
            return False, "stale_run", runtime
        if current_phase not in {"scheduled", "running"}:
            runtime["last_transition_result"] = f"invalid_phase_{current_phase or 'none'}"
            return False, f"invalid_phase_{current_phase or 'none'}", runtime
        runtime.update(
            {
                "version": SYNC_RUNTIME_VERSION,
                "current_run_id": "",
                "current_phase": action,
                "finished_at": now,
                "last_transition_at": now,
                "last_command_key": command_key,
                "last_transition_result": action,
                "last_terminal_run_id": sync_run_id,
                "last_terminal_phase": action,
                "last_terminal_at": now,
            }
        )
        return True, action, runtime

    runtime["last_transition_result"] = "unsupported_action"
    return False, "unsupported_action", runtime


def _is_duplicate_sync_command(*, account, action: str, command_key: str) -> bool:
    trace = _sync_trace(account)
    if trace.get("action") != action or trace.get("command_key") != command_key:
        return False
    raw_at = trace.get("at")
    if not raw_at:
        return True
    try:
        occurred_at = timezone.datetime.fromisoformat(str(raw_at).replace("Z", "+00:00"))
        if occurred_at.tzinfo is None:
            occurred_at = timezone.make_aware(occurred_at, timezone.get_current_timezone())
    except Exception:
        return True
    return max(0, int((timezone.now() - occurred_at).total_seconds())) <= SYNC_DEDUPE_WINDOW_SECONDS


def link_account_external_source(*, account, data: dict):
    account.link_external_account(**data)
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_EXTERNAL_LINKED,
        payload=build_account_sync_payload(account=account, change="link_external_source"),
        metadata={"source": "accounts.views.link_external_source"},
    )


def unlink_account_external_source(account):
    previous = {"provider": account.provider, "external_id": account.external_id}
    account.unlink_external_account(clear_metadata=False)
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_EXTERNAL_UNLINKED,
        payload=build_account_lifecycle_payload(
            account=account,
            change="unlink_external_source",
            extra={"previous": previous},
        ),
        metadata={"source": "accounts.views.unlink_external_source"},
    )
    return previous


def schedule_account_sync(*, account, data: dict):
    command_key = _sync_command_key(account=account, action="schedule", data=data, metadata=None)
    sync_run_id = _normalize_sync_run_id(data.get("sync_run_id")) or command_key[:32] or uuid.uuid4().hex
    previous_next_sync_at = account.next_sync_at
    previous_sync_status = account.sync_status
    previous_last_sync_status_at = account.last_sync_status_at
    next_sync_at = account.schedule_next_sync(
        run_at=data.get("run_at"),
        delay_minutes=data.get("delay_minutes", 30),
        commit=False,
    )
    applied, result, runtime = _advance_sync_runtime(
        account=account,
        action="schedule",
        sync_run_id=sync_run_id,
        command_key=command_key,
    )
    _set_sync_runtime(account, runtime)
    effective_run_id = (
        _normalize_sync_run_id(runtime.get("current_run_id"))
        or _normalize_sync_run_id(runtime.get("last_terminal_run_id"))
        or sync_run_id
    )
    if applied:
        account.save(update_fields=["next_sync_at", "last_sync_status_at", "sync_status", "sync_runtime", "updated_at"])
    else:
        account.next_sync_at = previous_next_sync_at
        account.sync_status = previous_sync_status
        account.last_sync_status_at = previous_last_sync_status_at
        next_sync_at = previous_next_sync_at or next_sync_at

    metadata = {"source": "accounts.views.schedule_sync", "sync_run_id": effective_run_id, "transition_result": result}
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_SYNC_SCHEDULED,
        payload=build_account_sync_payload(
            account=account,
            change="schedule_sync",
            extra={"next_sync_at": next_sync_at.isoformat(), "sync_run_id": effective_run_id, "transition_result": result},
        ),
        metadata=metadata,
    )
    return next_sync_at


def mark_account_sync_running(*, account, data: dict, metadata: dict | None = None):
    event_metadata = _merge_sync_metadata(metadata, source="accounts.views.mark_sync_running")
    command_key = _sync_command_key(account=account, action="running", data=data, metadata=event_metadata)
    if _is_duplicate_sync_command(account=account, action="running", command_key=command_key):
        return account

    sync_run_id = _resolve_sync_run_id(
        account=account,
        action="running",
        data=data,
        metadata=event_metadata,
        command_key=command_key,
    )
    event_metadata["sync_run_id"] = sync_run_id
    applied, transition_result, runtime = _advance_sync_runtime(
        account=account,
        action="running",
        sync_run_id=sync_run_id,
        command_key=command_key,
    )
    _set_sync_runtime(account, runtime)

    if not applied:
        _record_sync_trace(
            account=account,
            action="running",
            command_key=command_key,
            metadata=event_metadata,
            result=transition_result,
        )
        account.save(update_fields=["provider_metadata", "sync_runtime"])
        return account

    sync_cursor = data.get("sync_cursor")
    next_sync_at = data.get("next_sync_at")
    if sync_cursor is not None:
        account.sync_cursor = sync_cursor
    if next_sync_at is not None:
        account.next_sync_at = next_sync_at
    account.mark_sync_running(commit=False)
    _record_sync_trace(account=account, action="running", command_key=command_key, metadata=event_metadata, result="applied")
    account.save(
        update_fields=[
            "sync_cursor",
            "next_sync_at",
            "sync_status",
            "last_sync_status_at",
            "provider_metadata",
            "sync_runtime",
            "updated_at",
        ]
    )

    publish_account_sync_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
        change="mark_sync_running",
        extra={"sync_cursor": account.sync_cursor, "sync_run_id": sync_run_id},
        metadata=event_metadata,
    )
    publish_account_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STARTED,
        payload=build_account_sync_payload(
            account=account,
            change="sync_started",
            extra={"sync_cursor": account.sync_cursor, "sync_run_id": sync_run_id},
        ),
        metadata=event_metadata,
    )
    return account


def mark_account_sync_success(*, account, data: dict, metadata: dict | None = None):
    event_metadata = _merge_sync_metadata(metadata, source="accounts.views.mark_sync_success")
    command_key = _sync_command_key(account=account, action="success", data=data, metadata=event_metadata)
    if _is_duplicate_sync_command(account=account, action="success", command_key=command_key):
        return account

    sync_run_id = _resolve_sync_run_id(
        account=account,
        action="success",
        data=data,
        metadata=event_metadata,
        command_key=command_key,
    )
    event_metadata["sync_run_id"] = sync_run_id
    applied, transition_result, runtime = _advance_sync_runtime(
        account=account,
        action="success",
        sync_run_id=sync_run_id,
        command_key=command_key,
    )
    _set_sync_runtime(account, runtime)

    if not applied:
        _record_sync_trace(
            account=account,
            action="success",
            command_key=command_key,
            metadata=event_metadata,
            result=transition_result,
        )
        account.save(update_fields=["provider_metadata", "sync_runtime"])
        return account

    if "sync_cursor" in data:
        account.sync_cursor = data.get("sync_cursor") or ""
    if "provider_metadata" in data:
        merged_metadata = dict(account.provider_metadata or {})
        merged_metadata.update(data.get("provider_metadata") or {})
        account.provider_metadata = merged_metadata
    if data.get("next_sync_at") is not None:
        account.next_sync_at = data["next_sync_at"]

    account.mark_sync_ok(commit=False, duration_ms=data.get("duration_ms", 0))
    _record_sync_trace(account=account, action="success", command_key=command_key, metadata=event_metadata, result="applied")
    account.save(
        update_fields=[
            "sync_status",
            "sync_error_message",
            "last_sync_at",
            "last_sync_status_at",
            "sync_attempts",
            "last_sync_duration_ms",
            "sync_cursor",
            "provider_metadata",
            "sync_runtime",
            "next_sync_at",
            "updated_at",
        ]
    )

    publish_account_sync_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
        change="mark_sync_success",
        extra={"duration_ms": account.last_sync_duration_ms, "sync_run_id": sync_run_id},
        metadata=event_metadata,
    )
    publish_account_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_SYNC_SUCCEEDED,
        payload=build_account_sync_payload(
            account=account,
            change="sync_succeeded",
            extra={"duration_ms": account.last_sync_duration_ms, "sync_run_id": sync_run_id},
        ),
        metadata=event_metadata,
    )
    return account


def mark_account_sync_error(*, account, data: dict, metadata: dict | None = None):
    event_metadata = _merge_sync_metadata(metadata, source="accounts.views.mark_sync_error")
    command_key = _sync_command_key(account=account, action="error", data=data, metadata=event_metadata)
    if _is_duplicate_sync_command(account=account, action="error", command_key=command_key):
        return account

    sync_run_id = _resolve_sync_run_id(
        account=account,
        action="error",
        data=data,
        metadata=event_metadata,
        command_key=command_key,
    )
    event_metadata["sync_run_id"] = sync_run_id
    applied, transition_result, runtime = _advance_sync_runtime(
        account=account,
        action="error",
        sync_run_id=sync_run_id,
        command_key=command_key,
    )
    _set_sync_runtime(account, runtime)

    if not applied:
        _record_sync_trace(
            account=account,
            action="error",
            command_key=command_key,
            metadata=event_metadata,
            result=transition_result,
        )
        account.save(update_fields=["provider_metadata", "sync_runtime"])
        return account

    next_sync_at = data.get("next_sync_at")
    retry_in_minutes = data.get("retry_in_minutes")
    account.mark_sync_error(message=data["message"], commit=False)
    if next_sync_at is not None:
        account.next_sync_at = next_sync_at
    elif retry_in_minutes:
        account.schedule_next_sync(delay_minutes=retry_in_minutes, commit=False)
    _record_sync_trace(account=account, action="error", command_key=command_key, metadata=event_metadata, result="applied")
    account.save(
        update_fields=[
            "sync_status",
            "sync_error_message",
            "last_sync_status_at",
            "sync_attempts",
            "next_sync_at",
            "provider_metadata",
            "sync_runtime",
            "updated_at",
        ]
    )

    payload_extra = {
        "message": account.sync_error_message,
        "next_sync_at": account.next_sync_at.isoformat() if account.next_sync_at else None,
        "sync_run_id": sync_run_id,
    }
    publish_account_sync_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
        change="mark_sync_error",
        extra=payload_extra,
        metadata=event_metadata,
    )
    publish_account_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_SYNC_FAILED,
        payload=build_account_sync_payload(
            account=account,
            change="sync_failed",
            extra=payload_extra,
        ),
        metadata=event_metadata,
    )
    return account


def mark_account_sync_stale(account, *, metadata: dict | None = None):
    event_metadata = _merge_sync_metadata(metadata, source="accounts.views.mark_sync_stale")
    command_key = _sync_command_key(account=account, action="stale", data={}, metadata=event_metadata)
    if _is_duplicate_sync_command(account=account, action="stale", command_key=command_key):
        return account

    sync_run_id = _resolve_sync_run_id(
        account=account,
        action="stale",
        data={},
        metadata=event_metadata,
        command_key=command_key,
    )
    event_metadata["sync_run_id"] = sync_run_id
    applied, transition_result, runtime = _advance_sync_runtime(
        account=account,
        action="stale",
        sync_run_id=sync_run_id,
        command_key=command_key,
    )
    _set_sync_runtime(account, runtime)

    if not applied:
        _record_sync_trace(
            account=account,
            action="stale",
            command_key=command_key,
            metadata=event_metadata,
            result=transition_result,
        )
        account.save(update_fields=["provider_metadata", "sync_runtime"])
        return account

    account.mark_sync_stale(commit=False)
    _record_sync_trace(account=account, action="stale", command_key=command_key, metadata=event_metadata, result="applied")
    account.save(update_fields=["sync_status", "last_sync_status_at", "provider_metadata", "sync_runtime", "updated_at"])
    publish_account_sync_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
        change="mark_sync_stale",
        extra={"sync_run_id": sync_run_id},
        metadata=event_metadata,
    )
    return account
