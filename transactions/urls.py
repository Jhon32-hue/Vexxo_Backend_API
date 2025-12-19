from django.urls import path, include
from rest_framework.routers import DefaultRouter
from transactions.Views import (
    TransactionViewSet,
    TagViewSet,
    IncomeSourceViewSet,
    ScheduledPaymentViewSet,
)

router = DefaultRouter()
router.register(r'transacciones', TransactionViewSet, basename='transaction')
router.register(r'etiquetas', TagViewSet, basename='tag')
router.register(r'fuentes-ingreso', IncomeSourceViewSet, basename='income-source')
router.register(r'pagos-programados', ScheduledPaymentViewSet, basename='scheduled-payment')

urlpatterns = [
    path('', include(router.urls)),
]
