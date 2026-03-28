"""
Pruebas base del dominio de identidad.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from identity.users.domain import get_plan_capabilities, get_user_event_catalog
from identity.users.serializers.user_serializer import UserRegisterSerializer
from identity.users.services.oauth_service import get_supported_social_providers

User = get_user_model()


class IdentityUsersTests(TestCase):
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
