from __future__ import annotations

import base64
import binascii
import hashlib
import json
import secrets
import struct
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone

import cbor2
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509.oid import ObjectIdentifier
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from pyasn1.codec.der.decoder import decode as der_decode
from pyasn1.type import univ


class PlatformAttestationError(ValueError):
    pass


@dataclass(frozen=True)
class PlatformAttestationResult:
    provider: str
    public_key_b64: str = ""
    key_id: str = ""
    counter: int = 0
    summary: dict | None = None


def _decode_b64(value: str) -> bytes:
    text = str(value or "").strip()
    try:
        return base64.b64decode(text + "=" * (-len(text) % 4), validate=True)
    except (ValueError, binascii.Error):
        try:
            return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        except (ValueError, binascii.Error) as exc:
            raise PlatformAttestationError("invalid_base64") from exc


def decode_play_integrity_token(*, token: str, expected_request_hash: str) -> PlatformAttestationResult:
    package_names = set(getattr(settings, "PLAY_INTEGRITY_PACKAGE_NAMES", []))
    service_account_json = str(getattr(settings, "PLAY_INTEGRITY_SERVICE_ACCOUNT_JSON", "") or "").strip()
    required_verdict = str(getattr(settings, "PLAY_INTEGRITY_REQUIRED_DEVICE_VERDICT", "MEETS_DEVICE_INTEGRITY"))
    if not package_names or not service_account_json:
        raise ImproperlyConfigured("Play Integrity no esta configurado.")
    try:
        account_info = json.loads(service_account_json)
        credentials = service_account.Credentials.from_service_account_info(
            account_info,
            scopes=["https://www.googleapis.com/auth/playintegrity"],
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise ImproperlyConfigured("PLAY_INTEGRITY_SERVICE_ACCOUNT_JSON es invalido.") from exc

    last_error = None
    decoded = None
    resolved_package = ""
    session = AuthorizedSession(credentials)
    for package_name in package_names:
        response = session.post(
            f"https://playintegrity.googleapis.com/v1/{package_name}:decodeIntegrityToken",
            json={"integrity_token": token},
            timeout=15,
        )
        if response.ok:
            decoded = response.json().get("tokenPayloadExternal") or {}
            resolved_package = package_name
            break
        last_error = f"google_http_{response.status_code}"
    if decoded is None:
        raise PlatformAttestationError(last_error or "google_decode_failed")

    request_details = decoded.get("requestDetails") or {}
    app_integrity = decoded.get("appIntegrity") or {}
    device_integrity = decoded.get("deviceIntegrity") or {}
    package_name = str(app_integrity.get("packageName") or request_details.get("requestPackageName") or "")
    if package_name != resolved_package or package_name not in package_names:
        raise PlatformAttestationError("package_mismatch")
    if not secrets.compare_digest(str(request_details.get("requestHash") or ""), expected_request_hash):
        raise PlatformAttestationError("request_hash_mismatch")
    if app_integrity.get("appRecognitionVerdict") != "PLAY_RECOGNIZED":
        raise PlatformAttestationError("app_not_recognized")
    verdicts = set(device_integrity.get("deviceRecognitionVerdict") or [])
    if required_verdict and required_verdict not in verdicts:
        raise PlatformAttestationError("device_integrity_not_met")
    timestamp_ms = int(request_details.get("timestampMillis") or 0)
    now_ms = int(datetime.now(tz=datetime_timezone.utc).timestamp() * 1000)
    if timestamp_ms <= 0 or abs(now_ms - timestamp_ms) > 5 * 60 * 1000:
        raise PlatformAttestationError("stale_integrity_verdict")
    return PlatformAttestationResult(
        provider="play_integrity",
        summary={
            "package_name": package_name,
            "app_recognition": "PLAY_RECOGNIZED",
            "device_verdicts": sorted(verdicts),
        },
    )


def _verify_certificate_signature(certificate: x509.Certificate, issuer: x509.Certificate) -> None:
    public_key = issuer.public_key()
    if isinstance(public_key, rsa.RSAPublicKey):
        public_key.verify(
            certificate.signature,
            certificate.tbs_certificate_bytes,
            padding.PKCS1v15(),
            certificate.signature_hash_algorithm,
        )
    elif isinstance(public_key, ec.EllipticCurvePublicKey):
        public_key.verify(
            certificate.signature,
            certificate.tbs_certificate_bytes,
            ec.ECDSA(certificate.signature_hash_algorithm),
        )
    else:
        raise PlatformAttestationError("unsupported_certificate_key")


def _collect_octet_strings(value) -> list[bytes]:
    if isinstance(value, univ.OctetString):
        return [bytes(value)]
    output: list[bytes] = []
    if hasattr(value, "values"):
        for child in value.values():
            output.extend(_collect_octet_strings(child))
    return output


def verify_app_attest_object(
    *,
    attestation_object_b64: str,
    key_id: str,
    challenge_nonce: bytes,
) -> PlatformAttestationResult:
    app_id = str(getattr(settings, "APPLE_APP_ATTEST_APP_ID", "") or "").strip()
    root_pem = str(getattr(settings, "APPLE_APP_ATTEST_ROOT_CA_PEM", "") or "").strip()
    environment = str(getattr(settings, "APPLE_APP_ATTEST_ENVIRONMENT", "development") or "development").lower()
    if not app_id or not root_pem:
        raise ImproperlyConfigured("Apple App Attest no esta configurado.")
    try:
        attestation = cbor2.loads(_decode_b64(attestation_object_b64))
        auth_data = bytes(attestation["authData"])
        x5c = attestation["attStmt"]["x5c"]
        leaf = x509.load_der_x509_certificate(bytes(x5c[0]))
        intermediate = x509.load_der_x509_certificate(bytes(x5c[1]))
        root = x509.load_pem_x509_certificate(root_pem.encode("utf-8"))
    except (KeyError, IndexError, TypeError, ValueError, cbor2.CBORDecodeError) as exc:
        raise PlatformAttestationError("invalid_attestation_object") from exc
    if attestation.get("fmt") != "apple-appattest":
        raise PlatformAttestationError("invalid_attestation_format")
    if leaf.issuer != intermediate.subject or intermediate.issuer != root.subject:
        raise PlatformAttestationError("invalid_certificate_chain")
    _verify_certificate_signature(leaf, intermediate)
    _verify_certificate_signature(intermediate, root)

    now = datetime.now(tz=datetime_timezone.utc)
    for certificate in (leaf, intermediate):
        if not (certificate.not_valid_before_utc <= now <= certificate.not_valid_after_utc):
            raise PlatformAttestationError("expired_certificate")

    client_data_hash = hashlib.sha256(challenge_nonce).digest()
    expected_nonce = hashlib.sha256(auth_data + client_data_hash).digest()
    extension = leaf.extensions.get_extension_for_oid(ObjectIdentifier("1.2.840.113635.100.8.2"))
    try:
        decoded_extension, remainder = der_decode(extension.value.value)
    except Exception as exc:
        raise PlatformAttestationError("invalid_nonce_extension") from exc
    octets = _collect_octet_strings(decoded_extension)
    if remainder or expected_nonce not in octets:
        raise PlatformAttestationError("nonce_mismatch")

    public_key = leaf.public_key()
    if not isinstance(public_key, ec.EllipticCurvePublicKey) or public_key.curve.name != "secp256r1":
        raise PlatformAttestationError("invalid_attested_key")
    public_key_bytes = public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    key_id_bytes = _decode_b64(key_id)
    if not secrets.compare_digest(hashlib.sha256(public_key_bytes).digest(), key_id_bytes):
        raise PlatformAttestationError("key_id_mismatch")
    if len(auth_data) < 55:
        raise PlatformAttestationError("invalid_authenticator_data")
    if not secrets.compare_digest(auth_data[:32], hashlib.sha256(app_id.encode("utf-8")).digest()):
        raise PlatformAttestationError("app_id_mismatch")
    if struct.unpack(">I", auth_data[33:37])[0] != 0:
        raise PlatformAttestationError("invalid_initial_counter")
    expected_aaguid = b"appattestdevelop" if environment == "development" else b"appattest" + (b"\x00" * 7)
    if not secrets.compare_digest(auth_data[37:53], expected_aaguid):
        raise PlatformAttestationError("environment_mismatch")
    credential_length = struct.unpack(">H", auth_data[53:55])[0]
    credential_id = auth_data[55 : 55 + credential_length]
    if not secrets.compare_digest(credential_id, key_id_bytes):
        raise PlatformAttestationError("credential_id_mismatch")
    return PlatformAttestationResult(
        provider="app_attest",
        public_key_b64=base64.b64encode(public_key_bytes).decode("ascii"),
        key_id=key_id,
        counter=0,
        summary={"environment": environment, "app_id_hash_verified": True},
    )
