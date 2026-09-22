from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

ALGORITHM = "AES-256-GCM+ENVELOPE-v1"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(str(value).encode("ascii"))


def configured_keyring() -> dict[str, bytes]:
    raw = getattr(settings, "SECURITY_ENCRYPTION_KEYS", {}) or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ImproperlyConfigured("SECURITY_ENCRYPTION_KEYS_JSON is not valid JSON.") from exc
    result = {}
    for version, encoded_key in raw.items():
        if not encoded_key:
            continue
        try:
            key = _b64decode(encoded_key)
        except Exception as exc:
            raise ImproperlyConfigured(f"Encryption key {version!s} is not valid base64.") from exc
        if len(key) != 32:
            raise ImproperlyConfigured(f"Encryption key {version!s} must decode to 32 bytes.")
        result[str(version)] = key
    return result


def active_key_version() -> str:
    return str(getattr(settings, "SECURITY_ENCRYPTION_ACTIVE_KEY_VERSION", "") or "").strip()


def encryption_status() -> dict:
    versions = sorted(configured_keyring())
    active = active_key_version()
    return {"configured": bool(active and active in versions), "active_version": active, "read_versions": versions}


def _resolve_key(version: str) -> bytes:
    key = configured_keyring().get(str(version))
    if key is None:
        raise ImproperlyConfigured(f"Encryption key version {version!s} is not configured.")
    return key


def encrypt_secret(plaintext: str, *, aad: str) -> dict:
    version = active_key_version()
    kek = _resolve_key(version)
    aad_bytes = str(aad).encode("utf-8")
    dek = AESGCM.generate_key(bit_length=256)
    data_nonce = os.urandom(12)
    wrapped_key_nonce = os.urandom(12)
    ciphertext = AESGCM(dek).encrypt(data_nonce, str(plaintext).encode("utf-8"), aad_bytes)
    wrapped_key = AESGCM(kek).encrypt(wrapped_key_nonce, dek, aad_bytes)
    return {
        "algorithm": ALGORITHM,
        "key_version": version,
        "data_nonce": _b64encode(data_nonce),
        "ciphertext": _b64encode(ciphertext),
        "wrapped_key_nonce": _b64encode(wrapped_key_nonce),
        "wrapped_key": _b64encode(wrapped_key),
    }


def decrypt_secret(envelope: dict, *, aad: str) -> str:
    if envelope.get("algorithm") != ALGORITHM:
        raise ValueError("Unsupported encrypted envelope algorithm.")
    aad_bytes = str(aad).encode("utf-8")
    kek = _resolve_key(str(envelope["key_version"]))
    dek = AESGCM(kek).decrypt(
        _b64decode(envelope["wrapped_key_nonce"]),
        _b64decode(envelope["wrapped_key"]),
        aad_bytes,
    )
    plaintext = AESGCM(dek).decrypt(
        _b64decode(envelope["data_nonce"]),
        _b64decode(envelope["ciphertext"]),
        aad_bytes,
    )
    return plaintext.decode("utf-8")


def rewrap_envelope_key(envelope: dict, *, aad: str, target_version: str | None = None) -> dict:
    target = str(target_version or active_key_version())
    source = str(envelope["key_version"])
    if source == target:
        return dict(envelope)
    aad_bytes = str(aad).encode("utf-8")
    dek = AESGCM(_resolve_key(source)).decrypt(
        _b64decode(envelope["wrapped_key_nonce"]),
        _b64decode(envelope["wrapped_key"]),
        aad_bytes,
    )
    nonce = os.urandom(12)
    updated = dict(envelope)
    updated.update(
        key_version=target,
        wrapped_key_nonce=_b64encode(nonce),
        wrapped_key=_b64encode(AESGCM(_resolve_key(target)).encrypt(nonce, dek, aad_bytes)),
    )
    return updated


def rewrap_secret(envelope: dict, *, aad: str, target_version: str | None = None) -> dict:
    return rewrap_envelope_key(envelope, aad=aad, target_version=target_version)


def encrypt_bytes(plaintext: bytes, *, aad: str) -> tuple[bytes, dict]:
    version = active_key_version()
    kek = _resolve_key(version)
    aad_bytes = str(aad).encode("utf-8")
    dek = AESGCM.generate_key(bit_length=256)
    data_nonce = os.urandom(12)
    wrapped_key_nonce = os.urandom(12)
    ciphertext = AESGCM(dek).encrypt(data_nonce, bytes(plaintext), aad_bytes)
    wrapped_key = AESGCM(kek).encrypt(wrapped_key_nonce, dek, aad_bytes)
    return ciphertext, {
        "algorithm": ALGORITHM,
        "key_version": version,
        "data_nonce": _b64encode(data_nonce),
        "wrapped_key_nonce": _b64encode(wrapped_key_nonce),
        "wrapped_key": _b64encode(wrapped_key),
    }


def decrypt_bytes(ciphertext: bytes, envelope: dict, *, aad: str) -> bytes:
    if envelope.get("algorithm") != ALGORITHM:
        raise ValueError("Unsupported encrypted envelope algorithm.")
    aad_bytes = str(aad).encode("utf-8")
    kek = _resolve_key(str(envelope["key_version"]))
    dek = AESGCM(kek).decrypt(
        _b64decode(envelope["wrapped_key_nonce"]),
        _b64decode(envelope["wrapped_key"]),
        aad_bytes,
    )
    return AESGCM(dek).decrypt(_b64decode(envelope["data_nonce"]), bytes(ciphertext), aad_bytes)
