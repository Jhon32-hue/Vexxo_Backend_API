from django.apps import AppConfig


class ListenersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notifications.listeners'
    label = 'notification_listeners'

    def ready(self):
        from notifications.listeners import event_handlers  # noqa: F401
