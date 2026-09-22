from common.domain_events import EventContext
from common.outbox_runtime import enqueue_event_after_commit
from documents.ocr_requests.models import DocumentDomainEventOutbox


def enqueue_document_event(*, event_type: str, request, payload: dict):
    return enqueue_event_after_commit(
        model=DocumentDomainEventOutbox,
        namespace="docevt",
        context=EventContext.DOCUMENTS,
        event_type=event_type,
        aggregate_type="ocr_request",
        aggregate_id=request.pk,
        payload=payload,
        idempotency_key=f"docevt:{request.pk}:{event_type}:{request.attempt_count}",
    )
