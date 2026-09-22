from django.apps import AppConfig


class SecurityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "security"
    verbose_name = "Security foundation"

    def ready(self):
        from django.conf import settings
        from rest_framework_simplejwt import state

        from security.jwt_backend import build_jwt_token_backend

        state.token_backend = build_jwt_token_backend(
            {
                **settings.SIMPLE_JWT,
                **settings.JWT_KEYRING,
            }
        )
