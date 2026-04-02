from django.urls import include, path
from rest_framework.routers import DefaultRouter

from payments.scheduled_payments.views import PaymentScheduleRunViewSet, PaymentTemplateViewSet

router = DefaultRouter()
router.register(r"templates", PaymentTemplateViewSet, basename="payment-template")
router.register(r"runs", PaymentScheduleRunViewSet, basename="payment-schedule-run")

urlpatterns = [
    path("", include(router.urls)),
]
