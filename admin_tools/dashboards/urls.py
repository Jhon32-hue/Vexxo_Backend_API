from django.urls import path

from admin_tools.dashboards.views import OperationsDashboardView

urlpatterns = [
    path("operations/", OperationsDashboardView.as_view(), name="operations-dashboard"),
]
