from django.apps import AppConfig


class BudgetsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finance.budgets'
    label = 'budgets'

    def ready(self):
        import finance.budgets.event_handlers  # noqa: F401
