from django.urls import path

from integrations_stub.llm.views import InternalTransactionInferenceWorkerView


urlpatterns = [
    path(
        "transactions/inference/worker/",
        InternalTransactionInferenceWorkerView.as_view(),
        name="internal-transaction-inference-worker",
    ),
]
