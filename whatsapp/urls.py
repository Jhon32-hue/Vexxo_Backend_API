from django.urls import path
from whatsapp.views import WebhookView

urlpatterns = [
    path('whatsapp/webhook', WebhookView.as_view()),
]

