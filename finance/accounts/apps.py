from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "finance.accounts"
    label = "accounts"

    def ready(self):
        import finance.accounts.signals  # noqa
        import finance.accounts.event_handlers  # noqa
