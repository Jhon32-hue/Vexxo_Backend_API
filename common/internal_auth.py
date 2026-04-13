from __future__ import annotations

import secrets

from django.conf import settings
from rest_framework.exceptions import PermissionDenied


def assert_internal_token(request, setting_name: str, *, detail: str = "Unauthorized") -> None:
    expected = str(getattr(settings, setting_name, "") or "").strip()
    if not expected:
        raise PermissionDenied(f"Internal token `{setting_name}` is not configured.")

    provided = str(request.headers.get("X-Vexxo-Internal-Token") or "").strip()
    if not provided or not secrets.compare_digest(expected, provided):
        raise PermissionDenied(detail)
