# alerts/apps.py
from django.apps import AppConfig

class AlertsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "alerts.alerts"
    label = "alerts"

    def ready(self):
        # Fuerza la importación de los listeners para que el decorador @subscribe se ejecute
        from . import event_handlers  # noqa: F401
