from __future__ import annotations

import json
import re
from pathlib import PurePath
from urllib.parse import urlparse

from django.core.exceptions import ValidationError

from security.policies import SENSITIVE_METADATA_KEYS

_SAFE_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
_SAFE_ORDERING_RE = re.compile(r"^-?[A-Za-z][A-Za-z0-9_]{0,63}$")


def validate_safe_metadata(value, *, max_bytes: int = 16_384, max_depth: int = 5, max_items: int = 100):
    if value in (None, ""):
        return
    if not isinstance(value, (dict, list)):
        raise ValidationError("Metadata must be a JSON object or list.")
    try:
        encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError("Metadata must be valid JSON.") from exc
    if len(encoded) > max_bytes:
        raise ValidationError(f"Metadata exceeds {max_bytes} bytes.")

    def walk(node, depth: int):
        if depth > max_depth:
            raise ValidationError(f"Metadata exceeds maximum depth {max_depth}.")
        if isinstance(node, dict):
            if len(node) > max_items:
                raise ValidationError("Metadata contains too many fields.")
            for key, item in node.items():
                normalized = str(key).strip().lower()
                if not _SAFE_KEY_RE.fullmatch(str(key)):
                    raise ValidationError(f"Unsafe metadata key: {key!s}.")
                if normalized in SENSITIVE_METADATA_KEYS or normalized.endswith(("_token", "_secret", "_password", "_api_key")):
                    raise ValidationError(f"Sensitive field is not allowed in safe metadata: {key!s}.")
                walk(item, depth + 1)
        elif isinstance(node, list):
            if len(node) > max_items:
                raise ValidationError("Metadata contains too many list items.")
            for item in node:
                walk(item, depth + 1)
        elif node is not None and not isinstance(node, (str, int, float, bool)):
            raise ValidationError("Metadata contains an unsupported value type.")

    walk(value, 1)


def validate_https_url(value: str, *, allowed_hosts: set[str] | None = None, allow_http_local: bool = False) -> str:
    parsed = urlparse(str(value or "").strip())
    local_hosts = {"localhost", "127.0.0.1", "10.0.2.2"}
    valid_scheme = parsed.scheme == "https" or (allow_http_local and parsed.scheme == "http" and parsed.hostname in local_hosts)
    if not valid_scheme or not parsed.hostname or parsed.username or parsed.password:
        raise ValidationError("URL must use an allowed HTTPS origin.")
    if allowed_hosts and parsed.hostname.lower() not in {host.lower() for host in allowed_hosts}:
        raise ValidationError("URL host is not allowed.")
    return parsed.geturl()


def validate_safe_filename(value: str) -> str:
    name = str(value or "").strip()
    if not name or len(name) > 160 or PurePath(name).name != name or "\x00" in name:
        raise ValidationError("Unsafe file name.")
    return name


def validate_ordering(value: str, *, allowed_fields: set[str]) -> str:
    ordering = str(value or "").strip()
    field = ordering.removeprefix("-")
    if not _SAFE_ORDERING_RE.fullmatch(ordering) or field not in allowed_fields:
        raise ValidationError("Unsupported ordering field.")
    return ordering


def validate_external_payload(value, *, max_bytes: int = 131_072, max_depth: int = 8, max_items: int = 500):
    if value in (None, ""):
        return
    if not isinstance(value, (dict, list)):
        raise ValidationError("External payload must be a JSON object or list.")
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValidationError(f"External payload exceeds {max_bytes} bytes.")

    def walk(node, depth: int):
        if depth > max_depth:
            raise ValidationError(f"External payload exceeds maximum depth {max_depth}.")
        if isinstance(node, dict):
            if len(node) > max_items:
                raise ValidationError("External payload contains too many fields.")
            for item in node.values():
                walk(item, depth + 1)
        elif isinstance(node, list):
            if len(node) > max_items:
                raise ValidationError("External payload contains too many list items.")
            for item in node:
                walk(item, depth + 1)
        elif node is not None and not isinstance(node, (str, int, float, bool)):
            raise ValidationError("External payload contains an unsupported value type.")

    walk(value, 1)


def sanitize_external_payload(value):
    """Remove secrets from third-party JSON before persistence or logging."""
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            normalized = str(key).strip().lower()
            sensitive = normalized in SENSITIVE_METADATA_KEYS or normalized.endswith(
                ("_token", "_secret", "_password", "_api_key", "authorization")
            )
            sanitized[str(key)] = "[REDACTED]" if sensitive else sanitize_external_payload(item)
        validate_external_payload(sanitized)
        return sanitized
    if isinstance(value, list):
        sanitized = [sanitize_external_payload(item) for item in value]
        validate_external_payload(sanitized)
        return sanitized
    return value
