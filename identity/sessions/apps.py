from django.apps import AppConfig


class SessionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'identity.sessions'
    label = 'identity_sessions'

    def ready(self):
        from . import event_handlers  # noqa: F401
