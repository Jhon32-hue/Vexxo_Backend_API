from django.apps import AppConfig


class ScheduledPaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payments.scheduled_payments'
    label = 'scheduled_payments'
