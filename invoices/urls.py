from django.urls import path, include
from rest_framework.routers import DefaultRouter
from invoices.Views import FacturaViewSet, FacturaLineaViewSet

router = DefaultRouter()
router.register(r'facturas', FacturaViewSet, basename='factura')
router.register(r'factura-lineas', FacturaLineaViewSet, basename='factura-linea')

urlpatterns = [
    path('', include(router.urls)),
]

