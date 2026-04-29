from __future__ import annotations

from finance.transactions.Models import TransactionInferenceRequest
from finance.transactions.transaction_inference_service import (
    apply_transaction_inference_result,
    mark_transaction_inference_failed,
)


def process_stub_transaction_inference_request(
    *,
    inference_request_id,
    request_id: str = "",
    source: str = "",
) -> dict:
    inference_request = TransactionInferenceRequest.objects.select_related("account", "owner").filter(pk=inference_request_id).first()
    if inference_request is None:
        return {"result": "missing_inference_request"}
    if not inference_request.can_start_processing():
        return {
            "result": "skipped",
            "reason": "status_not_processable",
            "inference_request_id": str(inference_request.pk),
            "status": inference_request.status,
        }
    raw_payload = dict(inference_request.raw_payload or {})
    if raw_payload.get("transcription_failed"):
        inference_request, failed = mark_transaction_inference_failed(
            inference_request=inference_request,
            failure_stage="transcription",
            error=str(raw_payload.get("error") or "La transcripcion de audio fallo en el stub LLM."),
        )
        if not failed:
            return {
                "result": "skipped",
                "reason": "status_not_mutable_for_failure",
                "inference_request_id": str(inference_request.pk),
                "status": inference_request.status,
            }
        return {"result": "transcription_failed", "inference_request_id": str(inference_request.pk)}

    rows = raw_payload.get("normalized_rows") or raw_payload.get("rows") or []
    if not rows:
        inference_request, failed = mark_transaction_inference_failed(
            inference_request=inference_request,
            failure_stage="extraction",
            error="El stub LLM no recibio filas normalizadas para aplicar.",
        )
        if not failed:
            return {
                "result": "skipped",
                "reason": "status_not_mutable_for_failure",
                "inference_request_id": str(inference_request.pk),
                "status": inference_request.status,
            }
        return {"result": "extraction_failed", "inference_request_id": str(inference_request.pk)}

    inference_request, applied = apply_transaction_inference_result(
        inference_request=inference_request,
        rows=rows,
        transcript=str(raw_payload.get("transcript") or ""),
        transcript_confidence=raw_payload.get("transcript_confidence"),
        parser_version=str(raw_payload.get("parser_version") or "transactions.voice_parser.stub.v1"),
        provider_request_id=str(raw_payload.get("provider_request_id") or request_id or ""),
        provider_job_id=str(raw_payload.get("provider_job_id") or ""),
        provider_correlation_id=str(raw_payload.get("provider_correlation_id") or source or ""),
        raw_payload=raw_payload,
    )
    if not applied:
        return {
            "result": "skipped",
            "reason": "status_not_processable",
            "inference_request_id": str(inference_request.pk),
            "status": inference_request.status,
        }
    return {
        "result": "processed",
        "inference_request_id": str(inference_request.pk),
        "status": inference_request.status,
        "batch_id": str(inference_request.intake_batch_id or ""),
        "summary": inference_request.result_summary,
    }
