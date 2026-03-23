from django.apps import AppConfig


class DebtsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finance.debts'
    label = 'debts'
    def ready(self):  # noqa: D401
        # Import signals
        from . import signals  # noqa: F401
