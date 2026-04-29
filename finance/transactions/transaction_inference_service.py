from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction as db_tx
from django.utils import timezone
from rest_framework import serializers

from finance.accounts.models.account import Account
from finance.accounts.services.permission_service import user_can_post_transactions
from finance.transactions.Models import Transaction, TransactionInferenceRequest
from finance.transactions.transaction_intake_service import apply_intake_batch, receive_intake_batch


def _max_retries() -> int:
    return int(getattr(settings, "TRANSACTION_INFERENCE_MAX_RETRIES", 5) or 5)


def _to_confidence(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"))
    except (InvalidOperation, ValueError):
        return None


def _locked_inference_request(inference_request: TransactionInferenceRequest) -> TransactionInferenceRequest:
    return TransactionInferenceRequest.objects.select_for_update().get(pk=inference_request.pk)


@db_tx.atomic
def create_voice_transaction_inference_request(
    *,
    actor,
    account: Account,
    request_id: str,
    idempotency_key: str,
    audio_object_ref: str,
    audio_content_type: str = "",
    audio_duration_ms: int | None = None,
    language: str = "",
    provider: str = "voice_ai",
    raw_payload: dict | None = None,
) -> tuple[TransactionInferenceRequest, bool]:
    if not user_can_post_transactions(actor, account):
        raise serializers.ValidationError({"account": "No tienes permisos para registrar transacciones en esta cuenta."})
    inference_request, created = TransactionInferenceRequest.objects.get_or_create(
        idempotency_key=str(idempotency_key or "").strip(),
        defaults={
            "owner": account.owner,
            "requested_by": actor,
            "account": account,
            "source": TransactionInferenceRequest.Source.VOICE,
            "provider": str(provider or "voice_ai").strip().lower(),
            "request_id": str(request_id or "").strip(),
            "audio_object_ref": str(audio_object_ref or "").strip(),
            "audio_content_type": str(audio_content_type or "").strip(),
            "audio_duration_ms": audio_duration_ms,
            "language": str(language or "").strip(),
            "raw_payload": raw_payload or {},
        },
    )
    if not created:
        same_actor_scope = inference_request.account_id == account.pk and inference_request.owner_id == account.owner_id
        if not same_actor_scope:
            raise serializers.ValidationError({"idempotency_key": "El idempotency key ya existe para otra solicitud."})
        return inference_request, False

    from finance.transactions.transaction_inference_dispatch_service import dispatch_transaction_inference

    db_tx.on_commit(
        lambda: dispatch_transaction_inference(
            inference_request_id=inference_request.pk,
            request_id=inference_request.request_id,
            source="finance.transactions.transaction_inference_service.create_voice_transaction_inference_request",
        )
    )
    return inference_request, True


@db_tx.atomic
def retry_transaction_inference_request(*, inference_request: TransactionInferenceRequest, actor) -> TransactionInferenceRequest:
    if not user_can_post_transactions(actor, inference_request.account):
        raise serializers.ValidationError({"account": "No tienes permisos para reintentar esta solicitud."})
    inference_request = _locked_inference_request(inference_request)
    if inference_request.status not in {
        TransactionInferenceRequest.Status.TRANSCRIPTION_FAILED,
        TransactionInferenceRequest.Status.EXTRACTION_FAILED,
        TransactionInferenceRequest.Status.DEAD_LETTER,
    }:
        raise serializers.ValidationError({"status": "Solo puedes reintentar solicitudes fallidas."})
    inference_request.reset_for_retry()

    from finance.transactions.transaction_inference_dispatch_service import dispatch_transaction_inference

    db_tx.on_commit(
        lambda: dispatch_transaction_inference(
            inference_request_id=inference_request.pk,
            request_id=inference_request.request_id,
            source="finance.transactions.transaction_inference_service.retry_transaction_inference_request",
        )
    )
    return inference_request


@db_tx.atomic
def mark_transaction_inference_failed(
    *,
    inference_request: TransactionInferenceRequest,
    failure_stage: str,
    error: str,
) -> tuple[TransactionInferenceRequest, bool]:
    inference_request = _locked_inference_request(inference_request)
    if not inference_request.can_mark_failed():
        return inference_request, False
    status = (
        TransactionInferenceRequest.Status.TRANSCRIPTION_FAILED
        if failure_stage == "transcription"
        else TransactionInferenceRequest.Status.EXTRACTION_FAILED
    )
    inference_request.mark_failed(status=status, error=error, max_retries=_max_retries())
    return inference_request, True


def _build_voice_row(*, inference_request: TransactionInferenceRequest, row: dict, index: int, transcript: str, parser_version: str) -> dict:
    external_id = str(row.get("external_id") or f"{inference_request.pk}:item-{index}").strip()
    provider_event_id = str(row.get("provider_event_id") or external_id).strip()
    return {
        **row,
        "account_id": row.get("account_id") or inference_request.account_id,
        "external_id": external_id,
        "provider_event_id": provider_event_id,
        "provider_status": row.get("provider_status") or "inferred_pending_confirmation",
        "status": row.get("status") or Transaction.Status.PENDING,
        "confirmed": bool(row.get("confirmed", False)),
        "rail": row.get("rail") or Transaction.Rail.MANUAL,
        "channel": row.get("channel") or Transaction.Channel.VOICE,
        "data_origin": row.get("data_origin") or Transaction.DataOrigin.INFERRED,
        "needs_user_confirmation": bool(row.get("needs_user_confirmation", True)),
        "inference_status": row.get("inference_status") or "needs_confirmation",
        "message_id": row.get("message_id") or external_id,
        "sender_id": row.get("sender_id") or "user-audio",
        "received_at": row.get("received_at") or timezone.now().isoformat(),
        "parsed_text": row.get("parsed_text") or transcript,
        "parser_version": row.get("parser_version") or parser_version,
        "raw_payload": row.get("raw_payload") or {},
        "metadata": {
            "inference_request_id": str(inference_request.pk),
            "source": "transaction_inference",
            **(row.get("metadata") or {}),
        },
    }


@db_tx.atomic
def apply_transaction_inference_result(
    *,
    inference_request: TransactionInferenceRequest,
    rows: list[dict],
    transcript: str = "",
    transcript_confidence=None,
    parser_version: str = "transactions.voice_parser.v1",
    provider_request_id: str = "",
    provider_job_id: str = "",
    provider_correlation_id: str = "",
    raw_payload: dict | None = None,
) -> tuple[TransactionInferenceRequest, bool]:
    inference_request = _locked_inference_request(inference_request)
    if not inference_request.can_start_processing():
        return inference_request, False
    inference_request.mark_processing(
        provider_job_id=provider_job_id,
        provider_correlation_id=provider_correlation_id,
    )
    if not rows:
        return mark_transaction_inference_failed(
            inference_request=inference_request,
            failure_stage="extraction",
            error="La inferencia de voz no produjo movimientos estructurados.",
        )

    normalized_rows = [
        _build_voice_row(
            inference_request=inference_request,
            row=row,
            index=index,
            transcript=transcript,
            parser_version=parser_version,
        )
        for index, row in enumerate(rows, start=1)
    ]
    batch, _created = receive_intake_batch(
        provider=inference_request.provider,
        source=TransactionInferenceRequest.Source.VOICE.value,
        provider_account_id=str(inference_request.account_id),
        request_id=f"{inference_request.request_id}:voice-result",
        idempotency_key=f"{inference_request.idempotency_key}:voice-result:v1",
        rows=normalized_rows,
        raw_summary={
            "mode": "voice_inference",
            "inference_request_id": str(inference_request.pk),
        },
    )
    result = apply_intake_batch(batch=batch)
    partial = any(result.counts.get(key, 0) > 0 for key in ["failed", "corrected", "reversed"])

    inference_request.transcript = transcript or inference_request.transcript
    confidence = _to_confidence(transcript_confidence)
    if confidence is not None:
        inference_request.transcript_confidence = confidence
    inference_request.parser_version = parser_version or inference_request.parser_version
    inference_request.provider_request_id = provider_request_id or inference_request.provider_request_id
    inference_request.provider_job_id = provider_job_id or inference_request.provider_job_id
    inference_request.provider_correlation_id = provider_correlation_id or inference_request.provider_correlation_id
    inference_request.raw_payload = raw_payload or inference_request.raw_payload
    inference_request.normalized_payload = {"rows": normalized_rows}
    inference_request.save(
        update_fields=[
            "transcript",
            "transcript_confidence",
            "parser_version",
            "provider_request_id",
            "provider_job_id",
            "provider_correlation_id",
            "raw_payload",
            "normalized_payload",
            "updated_at",
        ]
    )
    inference_request.mark_applied(
        batch=batch,
        result_summary={"counts": dict(result.counts), "total": result.total},
        partial=partial,
    )
    return inference_request, True
