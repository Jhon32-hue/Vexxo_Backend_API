from django.urls import path

from payments.payment_intents.views import PaymentWorkerReportView


urlpatterns = [
    path("worker-report/", PaymentWorkerReportView.as_view(), name="payments-internal-worker-report"),
]
