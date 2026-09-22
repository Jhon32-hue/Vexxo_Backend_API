from __future__ import annotations

import contextvars
import logging
import re
import time
import uuid


_REQUEST_ID = contextvars.ContextVar("vexxo_request_id", default="")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
logger = logging.getLogger("vexxo.request")


def get_request_id() -> str:
    return _REQUEST_ID.get()


class RequestContextMiddleware:
    """Propaga un identificador seguro sin registrar payloads sensibles."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = str(request.headers.get("X-Request-ID") or "").strip()
        request_id = supplied if _SAFE_REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
        token = _REQUEST_ID.set(request_id)
        request.vexxo_request_id = request_id
        started = time.monotonic()
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            logger.info(
                "request.completed",
                extra={
                    "http_method": request.method,
                    "http_path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                },
            )
            return response
        finally:
            _REQUEST_ID.reset(token)
