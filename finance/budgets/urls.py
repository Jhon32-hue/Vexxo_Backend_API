from django.urls import include, path
from rest_framework.routers import DefaultRouter

from finance.budgets.Views import BudgetMonthlyOverviewView, CategoryBudgetViewSet, SharedBudgetViewSet

router = DefaultRouter()
router.register(r"presupuestos-categoria", CategoryBudgetViewSet, basename="category-budgets")
router.register(r"presupuestos-compartidos", SharedBudgetViewSet, basename="shared-budgets")

urlpatterns = [
    path("", include(router.urls)),
    path("resumen-mensual/", BudgetMonthlyOverviewView.as_view(), name="budget-monthly-overview"),
]
