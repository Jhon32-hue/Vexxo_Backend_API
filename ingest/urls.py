from django.urls import path
from ingest.views import IngestaTextoView

urlpatterns = [
    path('ingesta/texto', IngestaTextoView.as_view()),
]

