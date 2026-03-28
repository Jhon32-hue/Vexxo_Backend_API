# users/apps.py
from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "identity.users"
    label = "users"

    def ready(self):
        from identity.users import signals  # noqa
        from identity.users import event_handlers  # noqa
