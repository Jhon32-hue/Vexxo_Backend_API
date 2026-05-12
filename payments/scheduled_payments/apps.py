from django.apps import AppConfig


class ScheduledPaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payments.scheduled_payments'
    label = 'scheduled_payments'

    def ready(self):
        from payments.scheduled_payments import event_handlers  # noqa: F401
