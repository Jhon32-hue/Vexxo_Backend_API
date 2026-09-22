from django.urls import path
from reports.reports.views import BudgetMonthlySummaryView, CashflowView, GastosPorCategoriaView, ReportExportCreateView, ReportExportDownloadView, ReportSnapshotListCreateView

urlpatterns = [
    path('reportes/cashflow', CashflowView.as_view()),
    path('reportes/gastos-por-categoria', GastosPorCategoriaView.as_view()),
    path('reportes/presupuestos-mensuales', BudgetMonthlySummaryView.as_view()),
    path('snapshots/', ReportSnapshotListCreateView.as_view()),
    path('exports/', ReportExportCreateView.as_view()),
    path('exports/<uuid:export_id>/download/', ReportExportDownloadView.as_view()),
]
