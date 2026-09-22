from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.conf import settings


def verify_webhook_signature(*, provider: str, body: bytes, signature: str, timestamp: str = "", callback_url: str = "", authorization: str = "") -> bool:
    provider = (provider or "").strip().lower()
    if provider == "belvo":
        expected = os.getenv("OPEN_BANKING_BELVO_WEBHOOK_AUTHORIZATION", "").strip()
        return bool(expected and authorization and hmac.compare_digest(expected, authorization.strip()))
    if provider == "salt_edge":
        public_key = os.getenv("OPEN_BANKING_SALT_EDGE_CALLBACK_PUBLIC_KEY", "").replace("\\n", "\n").strip()
        if not public_key or not signature or not callback_url:
            return False
        try:
            key = serialization.load_pem_public_key(public_key.encode("utf-8"))
            key.verify(base64.b64decode(signature, validate=True), callback_url.encode() + b"|" + body, padding.PKCS1v15(), hashes.SHA256())
            return True
        except (ValueError, TypeError, InvalidSignature):
            return False

    secret = os.getenv("OPEN_BANKING_LOCAL_MOCK_WEBHOOK_SECRET", "").strip()
    provided = (signature or "").strip().removeprefix("sha256=")
    if not secret or not provided:
        return False
    normalized_timestamp = str(timestamp or "").strip()
    if normalized_timestamp:
        try:
            event_timestamp = int(normalized_timestamp)
        except ValueError:
            return False
        tolerance = max(1, int(getattr(settings, "OPEN_BANKING_WEBHOOK_TOLERANCE_SECONDS", 300)))
        if abs(int(time.time()) - event_timestamp) > tolerance:
            return False
        signed_payload = normalized_timestamp.encode("ascii") + b"." + body
    elif getattr(settings, "OPEN_BANKING_ALLOW_LEGACY_WEBHOOK_SIGNATURES", False):
        signed_payload = body
    else:
        return False
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)
