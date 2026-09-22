from __future__ import annotations

import socket
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from documents.files.models import DocumentFile
from documents.files.services import read_document_plaintext
from documents.ocr_requests.event_service import enqueue_document_event
from documents.ocr_requests.models import OcrFieldObservation, OcrRequest


@transaction.atomic
def request_ocr(
    *, owner, document: DocumentFile, idempotency_key: str,
    client_extracted_text: str = "", client_structured_hint: dict | None = None,
):
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValidationError({"idempotency_key": "Idempotency-Key es requerido."})
    if document.owner_id != owner.id or document.deleted_at is not None:
        raise ValidationError({"document": "Documento no disponible para este usuario."})
    request, created = OcrRequest.objects.get_or_create(
        owner=owner,
        idempotency_key=key,
        defaults={
            "document": document,
            "client_extracted_text": str(client_extracted_text or "")[:100000],
            "client_structured_hint": client_structured_hint or {},
        },
    )
    if not created and request.document_id != document.pk:
        raise ValidationError({"idempotency_key": "La clave ya fue usada para otro documento."})
    request._idempotent_replay = not created
    return request


def _normalize_hint(request: OcrRequest) -> tuple[str, dict, str]:
    text = "\n".join(line.strip() for line in request.client_extracted_text.splitlines() if line.strip())
    structured = dict(request.client_structured_hint or {})
    if text:
        return text, structured, "client_mlkit_text_v1"
    if request.document.content_type.startswith("text/"):
        return read_document_plaintext(request.document)[:100000].decode("utf-8", errors="replace").strip(), structured, "local_text_v1"
    return "", structured, "manual_review_v1"


def process_ocr_batch(*, limit: int = 25, worker_id: str = "") -> dict:
    worker_id = str(worker_id or f"{socket.gethostname()}:documents-ocr")[:64]
    stale_before = timezone.now() - timedelta(minutes=15)
    summary = {"claimed": 0, "succeeded": 0, "review_required": 0, "failed": 0}

    claimable = Q(status__in=[OcrRequest.Status.PENDING, OcrRequest.Status.FAILED]) | Q(
        status=OcrRequest.Status.PROCESSING,
        locked_at__lte=stale_before,
    )
    for request_id in list(
        OcrRequest.objects.filter(claimable).values_list("pk", flat=True)[: max(1, int(limit))]
    ):
        with transaction.atomic():
            request = (
                OcrRequest.objects.select_for_update(skip_locked=True)
                .select_related("document")
                .filter(pk=request_id)
                .first()
            )
            if request is None:
                continue
            is_stale = (
                request.status == OcrRequest.Status.PROCESSING
                and request.locked_at is not None
                and request.locked_at <= stale_before
            )
            if request.status not in {OcrRequest.Status.PENDING, OcrRequest.Status.FAILED} and not is_stale:
                continue
            request.status = OcrRequest.Status.PROCESSING
            request.locked_at = timezone.now()
            request.locked_by = worker_id
            request.attempt_count += 1
            request.save(update_fields=["status", "locked_at", "locked_by", "attempt_count", "updated_at"])
        summary["claimed"] += 1

        try:
            text, structured, engine = _normalize_hint(request)
            with transaction.atomic():
                request = OcrRequest.objects.select_for_update().select_related("document").get(pk=request_id)
                request.extracted_text = text
                request.structured_data = structured
                request.engine = engine
                request.status = OcrRequest.Status.SUCCEEDED if text else OcrRequest.Status.REVIEW_REQUIRED
                request.completed_at = timezone.now()
                request.last_error = ""
                request.locked_at = None
                request.locked_by = ""
                request.save()
                _record_structured_lineage(request=request, structured=structured, engine=engine)
                request.document.status = (
                    DocumentFile.Status.READY if text else DocumentFile.Status.REVIEW_REQUIRED
                )
                request.document.save(update_fields=["status", "updated_at"])
                enqueue_document_event(
                    event_type="documents.ocr.completed.v1" if text else "documents.ocr.review_required.v1",
                    request=request,
                    payload={
                        "owner_id": request.owner_id,
                        "document_id": str(request.document_id),
                        "ocr_request_id": str(request.pk),
                        "engine": engine,
                    },
                )
            summary["succeeded" if text else "review_required"] += 1
        except Exception as exc:
            with transaction.atomic():
                request = OcrRequest.objects.select_for_update().get(pk=request_id)
                request.status = OcrRequest.Status.FAILED
                request.last_error = str(exc)[:2000]
                request.locked_at = None
                request.locked_by = ""
                request.save(update_fields=["status", "last_error", "locked_at", "locked_by", "updated_at"])
            summary["failed"] += 1
    return summary


def _record_structured_lineage(*, request: OcrRequest, structured: dict, engine: str) -> None:
    for field_name, value in sorted((structured or {}).items()):
        OcrFieldObservation.objects.get_or_create(
            request=request,
            field_name=str(field_name)[:96],
            source="extractor",
            extractor_version=engine[:64],
            normalized_value=str(value)[:4000],
            defaults={"raw_value": str(value)[:4000]},
        )


@transaction.atomic
def correct_ocr_field(*, request: OcrRequest, owner, field_name: str, value, notes: str = ""):
    if request.owner_id != owner.pk:
        raise ValidationError({"request": "Solicitud OCR no disponible."})
    field = str(field_name or "").strip()[:96]
    if not field:
        raise ValidationError({"field_name": "field_name es requerido."})
    reason = str(notes or "").strip()
    if len(reason) < 5:
        raise ValidationError({"notes": "La correccion requiere un motivo de al menos 5 caracteres."})
    previous = request.field_observations.filter(field_name=field).order_by("-created_at").first()
    observation = OcrFieldObservation.objects.create(
        request=request,
        field_name=field,
        raw_value=str(value)[:4000],
        normalized_value=str(value)[:4000],
        confidence_score=100,
        source="user_correction",
        extractor_version="user.v1",
        supersedes=previous,
        corrected_by=owner,
        correction_reason=reason[:255],
    )
    structured = dict(request.structured_data or {})
    structured[field] = value
    request.structured_data = structured
    request.save(update_fields=["structured_data", "updated_at"])
    return observation
