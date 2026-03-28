from django.apps import AppConfig


class ConsentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'identity.consents'
    label = 'consents'

    def ready(self):
        from . import event_handlers  # noqa: F401
