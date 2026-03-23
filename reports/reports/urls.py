from django.urls import path
from reports.reports.views import CashflowView, GastosPorCategoriaView

urlpatterns = [
    path('reportes/cashflow', CashflowView.as_view()),
    path('reportes/gastos-por-categoria', GastosPorCategoriaView.as_view()),
]
