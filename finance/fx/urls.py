from django.urls import path, include
from rest_framework.routers import DefaultRouter
from finance.fx.views import TasaFXViewSet

router = DefaultRouter()
router.register(r'tasas-fx', TasaFXViewSet, basename='tasa-fx')

urlpatterns = [
    path('', include(router.urls)),
]
