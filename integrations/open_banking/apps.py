from django.apps import AppConfig


class OpenBankingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.open_banking"
    label = "open_banking"
    verbose_name = "Open banking integrations"
