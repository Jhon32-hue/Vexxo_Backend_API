from django.apps import AppConfig


class ListenersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'alerts.listeners'
    label = 'alert_listeners'
