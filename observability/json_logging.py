from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from common.request_context import get_request_id


class RequestContextFilter(logging.Filter):
    def filter(self, record):
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    EXTRA_FIELDS = (
        "request_id",
        "correlation_id",
        "causation_id",
        "http_method",
        "http_path",
        "status_code",
        "duration_ms",
        "event_type",
        "job_type",
        "retry_count",
        "queue_lag_seconds",
    )

    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self.EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value not in (None, ""):
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)
