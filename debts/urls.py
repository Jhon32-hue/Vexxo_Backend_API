from django.urls import path, include
from rest_framework.routers import DefaultRouter
from debts.views import DebtViewSet, DebtInstallmentViewSet

router = DefaultRouter()
router.register(r'deudas', DebtViewSet, basename='debt')
router.register(r'cuotas-deuda', DebtInstallmentViewSet, basename='debt-installment')

urlpatterns = [
    path('', include(router.urls)),
]
