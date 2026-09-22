from django.apps import AppConfig


class PaymentIntentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payments.payment_intents'
    label = 'payment_intents'

    def ready(self):
        from payments.payment_intents import signals  # noqa: F401
        from payments.payment_intents import event_handlers  # noqa: F401
