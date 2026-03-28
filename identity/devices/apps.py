from django.apps import AppConfig


class DevicesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'identity.devices'
    label = 'devices'

    def ready(self):
        return None
