from django.apps import AppConfig


class PaymentIntentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payments.payment_intents'
    label = 'payment_intents'
