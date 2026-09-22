from django.urls import path

from reports.monthly_reports.views import MonthlyReportCloseListCreateView


urlpatterns = [
    path("monthly-closes/", MonthlyReportCloseListCreateView.as_view(), name="monthly-report-closes"),
]
