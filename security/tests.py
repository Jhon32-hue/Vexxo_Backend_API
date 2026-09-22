import base64
import os
import time
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.apps import apps
from django.utils import timezone
from datetime import timedelta

from integrations.open_banking.security import verify_webhook_signature
from integrations.credentials.services import reveal_credential, revoke_credential, store_credential
from identity.users.services.communication_service import _resolve_password_reset_base_url
from identity.users.services.mfa_service import _totp_code, begin_totp_enrollment, confirm_totp_enrollment, verify_mfa_code
from security.encryption import decrypt_secret, encrypt_secret, rewrap_secret
from security.jwt_backend import MultiKeyTokenBackend
from security.rate_limits import consume_rate_limit
from security.validators import validate_https_url, validate_safe_filename, validate_safe_metadata
from security.policies import resolve_json_field_policy
from security.api_surface_audit import audit_api_surfaces
from security.models import SecurityAuditEvent, SecurityThrottleBucket
from security.retention import purge_security_retention


def _key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


class EncryptionTests(SimpleTestCase):
    @override_settings(
        SECURITY_ENCRYPTION_ACTIVE_KEY_VERSION="v1",
        SECURITY_ENCRYPTION_KEYS={"v1": _key(), "v2": _key()},
    )
    def test_envelope_roundtrip_and_rewrap(self):
        envelope = encrypt_secret("provider-token", aad="credential:1")
        self.assertNotIn("provider-token", str(envelope))
        self.assertEqual(decrypt_secret(envelope, aad="credential:1"), "provider-token")
        rotated = rewrap_secret(envelope, aad="credential:1", target_version="v2")
        self.assertEqual(rotated["key_version"], "v2")
        self.assertEqual(rotated["ciphertext"], envelope["ciphertext"])
        self.assertEqual(decrypt_secret(rotated, aad="credential:1"), "provider-token")

    def test_jwt_keyring_accepts_previous_key_after_rotation(self):
        keys = {"v1": "jwt-key-one-with-enough-entropy-123456", "v2": "jwt-key-two-with-enough-entropy-654321"}
        first = MultiKeyTokenBackend(algorithm="HS256", active_version="v1", signing_keys=keys)
        old_token = first.encode({"sub": "user-1", "exp": int(time.time()) + 60})
        rotated = MultiKeyTokenBackend(algorithm="HS256", active_version="v2", signing_keys=keys)
        self.assertEqual(rotated.decode(old_token)["sub"], "user-1")
        self.assertEqual(__import__("jwt").get_unverified_header(rotated.encode({"exp": int(time.time()) + 60}))["kid"], "v2")


class SecurityValidatorTests(SimpleTestCase):
    def test_sensitive_metadata_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_safe_metadata({"access_token": "unsafe"})

    def test_url_and_filename_policy(self):
        self.assertEqual(
            validate_https_url("https://app.vexxo.co/reset", allowed_hosts={"app.vexxo.co"}),
            "https://app.vexxo.co/reset",
        )
        with self.assertRaises(ValidationError):
            validate_https_url("https://evil.example/reset", allowed_hosts={"app.vexxo.co"})
        with self.assertRaises(ValidationError):
            validate_safe_filename("../secret.txt")

    @override_settings(
        BOOT_ENV="cloud",
        IDENTITY_PASSWORD_RESET_FRONTEND_URL="https://app.vexxo.co/reset",
        IDENTITY_PASSWORD_RESET_ALLOWED_HOSTS=["app.vexxo.co"],
    )
    def test_password_reset_redirect_falls_back_to_allowed_origin(self):
        self.assertEqual(
            _resolve_password_reset_base_url("https://phishing.example/reset"),
            "https://app.vexxo.co/reset",
        )


class SecurityPolicyCoverageTests(TestCase):
    def test_every_json_field_resolves_to_an_explicit_policy_shape(self):
        fields = []
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if field.__class__.__name__ == "JSONField":
                    policy = resolve_json_field_policy(model._meta.label, field.name)
                    self.assertTrue(policy.schema.endswith(".v1"))
                    self.assertIsNotNone(policy.classification)
                    self.assertIn(policy.validation_boundary.value, {"model", "service", "internal"})
                    self.assertIn(policy.validator_profile.value, {"safe_metadata", "external_payload", "internal_json"})
                    self.assertGreater(policy.max_bytes, 0)
                    fields.append(field)
        self.assertGreaterEqual(len(fields), 100)

    def test_api_filters_and_dynamic_ordering_are_allowlisted(self):
        audit = audit_api_surfaces()
        self.assertEqual(audit["unsafe_view_count"], 0)
        self.assertEqual(audit["unsafe_code_count"], 0)

    def test_retention_purges_old_audit_and_throttle_rows(self):
        event = SecurityAuditEvent.objects.create(event_type="test.old", severity="info")
        bucket = SecurityThrottleBucket.objects.create(
            scope="test", subject_hash="a" * 64,
            window_started_at=timezone.now() - timedelta(days=60),
        )
        cutoff = timezone.now() - timedelta(days=400)
        SecurityAuditEvent.objects.filter(pk=event.pk).update(created_at=cutoff)
        SecurityThrottleBucket.objects.filter(pk=bucket.pk).update(updated_at=timezone.now() - timedelta(days=60))
        result = purge_security_retention(now=timezone.now())
        self.assertGreaterEqual(result["deleted_total"], 2)
        self.assertFalse(SecurityAuditEvent.objects.filter(pk=event.pk).exists())
        self.assertFalse(SecurityThrottleBucket.objects.filter(pk=bucket.pk).exists())

    @override_settings(OPEN_BANKING_WEBHOOK_TOLERANCE_SECONDS=300, OPEN_BANKING_ALLOW_LEGACY_WEBHOOK_SIGNATURES=False)
    def test_webhook_timestamp_prevents_stale_replay(self):
        import hashlib
        import hmac

        body = b'{"event_id":"evt-1"}'
        timestamp = str(int(time.time()))
        signature = hmac.new(b"test-secret", timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {"OPEN_BANKING_LOCAL_MOCK_WEBHOOK_SECRET": "test-secret"}):
            self.assertTrue(
                verify_webhook_signature(provider="local_mock", body=body, signature=signature, timestamp=timestamp)
            )
            self.assertFalse(
                verify_webhook_signature(
                    provider="local_mock",
                    body=body,
                    signature=signature,
                    timestamp=str(int(timestamp) - 1000),
                )
            )


class DurableRateLimitTests(TestCase):
    def test_limit_is_persisted_and_blocks_excess(self):
        self.assertTrue(consume_rate_limit(scope="test", subject="user", limit=2, window_seconds=60).allowed)
        self.assertTrue(consume_rate_limit(scope="test", subject="user", limit=2, window_seconds=60).allowed)
        blocked = consume_rate_limit(scope="test", subject="user", limit=2, window_seconds=60)
        self.assertFalse(blocked.allowed)
        self.assertGreater(blocked.retry_after_seconds, 0)


@override_settings(
    SECURITY_ENCRYPTION_ACTIVE_KEY_VERSION="v1",
    SECURITY_ENCRYPTION_KEYS={"v1": _key()},
)
class IntegrationCredentialTests(TestCase):
    def test_secret_is_encrypted_and_revoke_blocks_reveal(self):
        user = get_user_model().objects.create_user(
            username="credential-owner",
            email="credential-owner@example.com",
            password="VexxoPass2026!",
        )
        credential = store_credential(
            owner=user,
            provider="local_test",
            credential_type="access_token",
            secret="provider-secret-token",
            external_reference="connection-1",
        )
        self.assertNotIn("provider-secret-token", str(credential.encrypted_payload))
        self.assertEqual(reveal_credential(credential), "provider-secret-token")
        credential = revoke_credential(credential)
        with self.assertRaises(ValueError):
            reveal_credential(credential)

    def test_totp_enrollment_and_recovery_code_are_one_time(self):
        user = get_user_model().objects.create_user(
            username="mfa-user",
            email="mfa-user@example.com",
            password="VexxoPass2026!",
        )
        method, secret, _uri = begin_totp_enrollment(user=user, current_password="VexxoPass2026!")
        code = _totp_code(secret, int(time.time()) // 30)
        method, recovery_codes = confirm_totp_enrollment(user=user, code=code)
        self.assertEqual(method.status, "active")
        verified, used_method = verify_mfa_code(user=user, code=recovery_codes[0])
        self.assertTrue(verified)
        self.assertEqual(used_method, "recovery_code")
        self.assertEqual(verify_mfa_code(user=user, code=recovery_codes[0]), (False, "invalid_code"))

    def test_email_password_reset_requires_mfa_for_enrolled_user(self):
        from django.contrib.auth.tokens import PasswordResetTokenGenerator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        from identity.users.serializers.auth_flow_serializer import PasswordResetConfirmSerializer

        user = get_user_model().objects.create_user(
            username="mfa-reset-user", email="mfa-reset@example.com", password="VexxoPass2026!"
        )
        _method, secret, _uri = begin_totp_enrollment(user=user, current_password="VexxoPass2026!")
        _method, recovery_codes = confirm_totp_enrollment(
            user=user, code=_totp_code(secret, int(time.time()) // 30)
        )
        payload = {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": PasswordResetTokenGenerator().make_token(user),
            "password": "RecoveredPass2026!",
            "password2": "RecoveredPass2026!",
        }
        without_mfa = PasswordResetConfirmSerializer(data=payload)
        self.assertFalse(without_mfa.is_valid())
        with_mfa = PasswordResetConfirmSerializer(data={**payload, "mfa_code": recovery_codes[0]})
        self.assertTrue(with_mfa.is_valid(), with_mfa.errors)
