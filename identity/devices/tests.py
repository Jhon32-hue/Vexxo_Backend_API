import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from unittest.mock import patch
from datetime import timedelta

from identity.devices.attestation import PlatformAttestationError
from identity.devices.models import DeviceAttestationStatus, DevicePlatformAttestationChallenge
from identity.devices.services import (
    expire_platform_attestations,
    issue_signature_challenge,
    register_or_update_device,
    revoke_platform_attestations,
    trust_device,
    verify_platform_attestation,
    verify_signature_challenge,
)
from identity.sessions.services import register_user_session

User = get_user_model()


class UserDeviceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="device-user", email="device@example.com", password="TestPass2026!")

    def test_register_or_update_device_creates_record(self):
        device = register_or_update_device(
            user=self.user,
            payload={"fingerprint": "fp-123", "device_type": "mobile", "platform": "android"},
        )
        self.assertEqual(device.user, self.user)
        self.assertEqual(device.fingerprint, "fp-123")

    def test_trust_device_updates_trust_level(self):
        device = register_or_update_device(user=self.user, payload={"fingerprint": "fp-456"})
        trust_device(device)
        device.refresh_from_db()
        self.assertEqual(device.trust_level, "trusted")

    def test_signed_challenge_proves_key_possession_once(self):
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        device = register_or_update_device(
            user=self.user,
            payload={
                "fingerprint": "fp-signed",
                "signing_algorithm": "ed25519",
                "signing_public_key": base64.b64encode(public_key).decode("ascii"),
            },
        )
        challenge, nonce = issue_signature_challenge(device=device, purpose="register_key")
        nonce_bytes = base64.urlsafe_b64decode(nonce + "=" * (-len(nonce) % 4))
        verify_signature_challenge(
            device=device,
            challenge_id=challenge.public_id,
            nonce=nonce,
            signature=base64.b64encode(private_key.sign(nonce_bytes)).decode("ascii"),
            purpose="register_key",
        )
        device.refresh_from_db()
        self.assertEqual(device.attestation_status, "key_verified")
        with self.assertRaises(ValueError):
            verify_signature_challenge(
                device=device,
                challenge_id=challenge.public_id,
                nonce=nonce,
                signature=base64.b64encode(private_key.sign(nonce_bytes)).decode("ascii"),
                purpose="register_key",
            )

    @override_settings(DEVICE_ATTESTATION_FAILURE_THRESHOLD=3)
    @patch("identity.devices.services.decode_play_integrity_token", side_effect=PlatformAttestationError("bad_verdict"))
    def test_repeated_attestation_anomalies_persist_and_revoke_sessions(self, _decode):
        device = register_or_update_device(user=self.user, payload={"fingerprint": "attestation-risk"})
        session = register_user_session(user=self.user, session_key="attestation-session", device=device)
        nonce_bytes = b"a" * 32
        nonce = base64.urlsafe_b64encode(nonce_bytes).decode("ascii").rstrip("=")
        challenge = DevicePlatformAttestationChallenge.objects.create(
            device=device,
            provider="play_integrity",
            nonce_hash=__import__("hashlib").sha256(nonce_bytes).hexdigest(),
            request_hash=__import__("hashlib").sha256(nonce_bytes).hexdigest(),
            expires_at=timezone.now() + timedelta(minutes=3),
        )
        for _ in range(3):
            with self.assertRaises(PlatformAttestationError):
                verify_platform_attestation(
                    device=device,
                    challenge_id=challenge.public_id,
                    provider="play_integrity",
                    nonce=nonce,
                    token="invalid",
                )
        challenge.refresh_from_db()
        device.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(challenge.failed_attempts, 3)
        self.assertEqual(device.attestation_status, "rejected")
        self.assertEqual(device.trust_level, "suspicious")
        self.assertEqual(session.status, "revoked")

    def test_expired_platform_attestation_downgrades_to_verified_key(self):
        device = register_or_update_device(
            user=self.user,
            payload={"fingerprint": "expired-attestation", "signing_public_key": "registered-key"},
        )
        device.key_verified_at = timezone.now() - timedelta(days=2)
        device.attestation_status = DeviceAttestationStatus.PLATFORM_VERIFIED
        device.platform_verified_at = timezone.now() - timedelta(days=2)
        device.platform_verification_expires_at = timezone.now() - timedelta(minutes=1)
        device.save()

        result = expire_platform_attestations()

        device.refresh_from_db()
        self.assertEqual(result["expired_attestations"], 1)
        self.assertEqual(device.attestation_status, DeviceAttestationStatus.KEY_VERIFIED)
        self.assertFalse(device.platform_verified_active)

    def test_bulk_attestation_revocation_closes_device_sessions(self):
        device = register_or_update_device(user=self.user, payload={"fingerprint": "bulk-attestation"})
        device.attestation_provider = "play_integrity"
        device.attestation_status = DeviceAttestationStatus.PLATFORM_VERIFIED
        device.platform_verified_at = timezone.now() - timedelta(days=1)
        device.platform_verification_expires_at = timezone.now() + timedelta(days=1)
        device.save()
        session = register_user_session(user=self.user, session_key="bulk-attestation-session", device=device)

        revoked = revoke_platform_attestations(provider="play_integrity")

        device.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(revoked, 1)
        self.assertEqual(device.attestation_status, DeviceAttestationStatus.REJECTED)
        self.assertEqual(session.status, "revoked")
        self.assertEqual(session.revocation_reason, "attestation_bulk_revoked")
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
