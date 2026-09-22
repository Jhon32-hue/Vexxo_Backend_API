from django.apps import AppConfig


class CredentialsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.credentials"
    label = "integration_credentials"
    verbose_name = "Integration credentials"
