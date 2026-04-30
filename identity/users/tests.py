"""
Pruebas base del dominio de identidad.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework.test import APIClient

from identity.devices.models import UserDevice
from identity.sessions.services import register_user_session
from identity.users.models import AuthChallengeStatus, UserAuthChallenge
from identity.users.domain import get_plan_capabilities, get_user_event_catalog
from identity.users.serializers.user_serializer import UserRegisterSerializer
from identity.users.services.oauth_service import get_supported_social_providers
from notifications.deliveries.models import NotificationDelivery

User = get_user_model()


class IdentityUsersTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_serializer_generates_username_and_splits_full_name(self):
        serializer = UserRegisterSerializer(
            data={
                "full_name": "Ada Lovelace",
                "email": "ada@example.com",
                "password": "VexxoPass2026!",
                "password2": "VexxoPass2026!",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()

        self.assertEqual(user.first_name, "Ada")
        self.assertEqual(user.last_name, "Lovelace")
        self.assertEqual(user.email, "ada@example.com")
        self.assertTrue(bool(user.username))

    def test_register_serializer_rejects_weak_password_without_upper_lower_digit(self):
        serializer = UserRegisterSerializer(
            data={
                "full_name": "Ada Lovelace",
                "email": "weak@example.com",
                "password": "solodebil",
                "password2": "solodebil",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("password", serializer.errors)

    def test_plan_capabilities_are_canonical_for_free(self):
        capabilities = get_plan_capabilities("free")
        self.assertEqual(capabilities["max_active_accounts"], 3)
        self.assertEqual(capabilities["max_primary_accounts"], 1)
        self.assertEqual(capabilities["max_investment_accounts"], 1)

    @override_settings(
        GOOGLE_OAUTH_ENABLED=False,
        GOOGLE_OAUTH_CLIENT_ID="",
        GOOGLE_OAUTH_CALLBACK_URL="",
        FACEBOOK_OAUTH_ENABLED=False,
        FACEBOOK_OAUTH_CLIENT_ID="",
        FACEBOOK_OAUTH_CALLBACK_URL="",
    )
    def test_social_provider_registry_includes_google_and_facebook(self):
        providers = get_supported_social_providers()
        codes = {item["provider"] for item in providers}
        self.assertEqual(codes, {"google", "facebook"})
        self.assertTrue(all("configured" in item for item in providers))

    def test_user_event_catalog_contains_registration_event(self):
        catalog = get_user_event_catalog()
        self.assertIn("users.registered.v1", catalog)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        APP_FRONTEND_URL="https://app.vexxo.test",
        IDENTITY_PASSWORD_RESET_FRONTEND_URL="https://app.vexxo.test/reset-password",
    )
    def test_password_reset_request_returns_generic_message_and_sends_email(self):
        user = User.objects.create_user(
            username="reset-user",
            email="reset@example.com",
            password="VexxoPass2026!",
        )
        response = self.client.post(
            "/api/identity/users/auth/password-reset/request/",
            {"email": user.email},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset-password", mail.outbox[0].body)

    def test_password_reset_confirm_updates_password(self):
        from django.contrib.auth.tokens import PasswordResetTokenGenerator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = User.objects.create_user(
            username="confirm-user",
            email="confirm@example.com",
            password="VexxoPass2026!",
        )
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = PasswordResetTokenGenerator().make_token(user)
        response = self.client.post(
            "/api/identity/users/auth/password-reset/confirm/",
            {
                "uid": uid,
                "token": token,
                "password": "OtraClave2026!",
                "password2": "OtraClave2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        user.refresh_from_db()
        self.assertTrue(user.check_password("OtraClave2026!"))

    def test_authenticated_user_can_set_password(self):
        user = User.objects.create_user(
            username="set-pass-user",
            email="set-pass@example.com",
            password="VexxoPass2026!",
        )
        self.client.force_authenticate(user)
        response = self.client.post(
            "/api/identity/users/auth/set-password/",
            {
                "new_password": "NuevaClave2026!",
                "new_password2": "NuevaClave2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        user.refresh_from_db()
        self.assertTrue(user.check_password("NuevaClave2026!"))

    @override_settings(
        IDENTITY_RECOVERY_DEBUG_REVEAL_CODE=True,
        IDENTITY_RECOVERY_CODE_TTL_SECONDS=120,
        IDENTITY_RECOVERY_MAX_ATTEMPTS=5,
    )
    def test_password_recovery_code_flow_uses_generic_request_and_updates_password(self):
        user = User.objects.create_user(
            username="otp-user",
            email="otp@example.com",
            password="VexxoPass2026!",
            phone_number="+57 300 123 4567",
        )
        request_response = self.client.post(
            "/api/identity/users/auth/password-recovery/request-code/",
            {"phone_number": "+57 3001234567"},
            format="json",
        )
        self.assertEqual(request_response.status_code, 200, request_response.data)
        challenge = UserAuthChallenge.objects.get(user=user)
        self.assertEqual(challenge.status, AuthChallengeStatus.PENDING)
        delivery = NotificationDelivery.objects.filter(owner=user, event_type="users.password_recovery.code_requested.v1").latest("created_at")
        debug_code = delivery.payload.get("debug_code")
        self.assertTrue(bool(debug_code))

        confirm_response = self.client.post(
            "/api/identity/users/auth/password-recovery/confirm-code/",
            {
                "phone_number": "+57 3001234567",
                "code": debug_code,
                "password": "OTPReset2026!",
                "password2": "OTPReset2026!",
            },
            format="json",
        )
        self.assertEqual(confirm_response.status_code, 200, confirm_response.data)
        challenge.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(challenge.status, AuthChallengeStatus.CONSUMED)
        self.assertTrue(user.check_password("OTPReset2026!"))

    @override_settings(IDENTITY_RECOVERY_DEBUG_REVEAL_CODE=True)
    def test_password_recovery_code_rejects_invalid_code(self):
        user = User.objects.create_user(
            username="otp-fail-user",
            email="otpfail@example.com",
            password="VexxoPass2026!",
            phone_number="+57 301 555 7788",
        )
        self.client.post(
            "/api/identity/users/auth/password-recovery/request-code/",
            {"phone_number": user.phone_number},
            format="json",
        )
        response = self.client.post(
            "/api/identity/users/auth/password-recovery/confirm-code/",
            {
                "phone_number": user.phone_number,
                "code": "000000",
                "password": "OTPReset2026!",
                "password2": "OTPReset2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

    @override_settings(
        IDENTITY_RECOVERY_DEBUG_REVEAL_CODE=True,
        IDENTITY_MESSAGE_BACKEND="local_stub",
        IDENTITY_STEP_UP_TRUST_DEVICE_ON_SUCCESS=True,
    )
    def test_step_up_flow_marks_session_verified_and_trusts_device(self):
        user = User.objects.create_user(
            username="step-up-user",
            email="stepup@example.com",
            password="VexxoPass2026!",
            phone_number="+57 300 777 1122",
        )
        device = UserDevice.objects.create(
            user=user,
            fingerprint="mobile-step-up",
            device_type="mobile",
            trust_level="unknown",
        )
        access = AccessToken.for_user(user)
        session = register_user_session(
            user=user,
            access_jti=str(access.get("jti", "")),
            refresh_jti="refresh-step-up",
            device=device,
            session_type="password",
            family_id="family-step-up",
        )
        self.assertTrue(session.requires_step_up)

        self.client.force_authenticate(user=user, token=access)
        request_response = self.client.post(
            "/api/identity/users/auth/step-up/request-code/",
            {"session_id": session.pk},
            format="json",
        )
        self.assertEqual(request_response.status_code, 200, request_response.data)
        delivery = NotificationDelivery.objects.filter(owner=user, event_type="users.step_up.code_requested.v1").latest("created_at")
        debug_code = delivery.payload.get("debug_code")
        self.assertTrue(bool(debug_code))

        confirm_response = self.client.post(
            "/api/identity/users/auth/step-up/confirm-code/",
            {"session_id": session.pk, "code": debug_code},
            format="json",
        )
        self.assertEqual(confirm_response.status_code, 200, confirm_response.data)
        session.refresh_from_db()
        device.refresh_from_db()
        self.assertFalse(session.requires_step_up)
        self.assertEqual(device.trust_level, "trusted")

    @override_settings(
        IDENTITY_RECOVERY_DEBUG_REVEAL_CODE=True,
        IDENTITY_RECOVERY_COOLDOWN_SECONDS=300,
    )
    def test_password_recovery_code_request_applies_cooldown(self):
        user = User.objects.create_user(
            username="cooldown-user",
            email="cooldown@example.com",
            password="VexxoPass2026!",
            phone_number="+57 300 111 2233",
        )
        first = self.client.post(
            "/api/identity/users/auth/password-recovery/request-code/",
            {"phone_number": user.phone_number},
            format="json",
        )
        second = self.client.post(
            "/api/identity/users/auth/password-recovery/request-code/",
            {"phone_number": user.phone_number},
            format="json",
        )
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertIn("retry_after_seconds", second.data)
