from django.urls import path

from observability.views import liveness_view, readiness_view


urlpatterns = [
    path("health/", liveness_view, name="runtime-health"),
    path("readiness/", readiness_view, name="runtime-readiness"),
]
