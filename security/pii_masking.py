import re
from collections.abc import Mapping, Sequence

from security.policies import SENSITIVE_METADATA_KEYS

_EMAIL_RE = re.compile(r"(?P<local>[^@\s]+)@(?P<domain>[^@\s]+)")
_TOKEN_RE = re.compile(r"(?i)\b(?:bearer\s+)?[A-Za-z0-9_-]{24,}(?:\.[A-Za-z0-9_-]{8,}){0,2}\b")


def mask_email(value: str) -> str:
    match = _EMAIL_RE.fullmatch(str(value or "").strip())
    if not match:
        return "***"
    return f"{match.group('local')[:1]}***@{match.group('domain')}"


def mask_phone(value: str) -> str:
    raw = str(value or "")
    digits = "".join(character for character in raw if character.isdigit())
    if len(digits) <= 4:
        return "***"
    prefix = "+" if raw.strip().startswith("+") else ""
    return f"{prefix}{digits[:2]}***{digits[-2:]}"


def mask_identifier(value: str, *, visible_suffix: int = 4) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    return f"***{raw[-visible_suffix:]}" if len(raw) > visible_suffix else "***"


def redact_text(value: str) -> str:
    text = _EMAIL_RE.sub(lambda match: mask_email(match.group(0)), str(value or ""))
    return _TOKEN_RE.sub("[REDACTED]", text)


def redact_mapping(value):
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            normalized = str(key).strip().lower()
            sensitive = normalized in SENSITIVE_METADATA_KEYS or normalized.endswith(
                ("_token", "_secret", "_password", "_api_key")
            )
            result[key] = "[REDACTED]" if sensitive else redact_mapping(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_mapping(item) for item in value]
    return redact_text(value) if isinstance(value, str) else value
