from django.apps import AppConfig


class EventingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "identity.eventing"
    label = "identity_eventing"
