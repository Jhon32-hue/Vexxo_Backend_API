from __future__ import annotations

import logging

from security.models import SecurityAuditEvent
from security.pii_masking import redact_mapping
from security.validators import validate_safe_metadata

logger = logging.getLogger(__name__)


def record_security_event(*, event_type: str, severity: str = SecurityAuditEvent.Severity.INFO, actor=None, request=None, source: str = "", target_type: str = "", target_id: str = "", metadata: dict | None = None) -> SecurityAuditEvent | None:
    try:
        safe_metadata = redact_mapping(metadata or {})
        try:
            validate_safe_metadata(safe_metadata)
        except Exception:
            safe_metadata = {"metadata_rejected": True}
        return SecurityAuditEvent.objects.create(
            event_type=event_type,
            severity=severity,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            request_id=str(getattr(request, "request_id", "") or ""),
            source=source,
            target_type=target_type,
            target_id=str(target_id or ""),
            safe_metadata=safe_metadata,
        )
    except Exception:
        logger.exception("security_audit_write_failed", extra={"security_event_type": event_type})
        return None
