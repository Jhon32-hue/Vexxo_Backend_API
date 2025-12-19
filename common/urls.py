from django.urls import path
from common.views import HealthView

urlpatterns = [
    path('salud', HealthView.as_view()),
]

