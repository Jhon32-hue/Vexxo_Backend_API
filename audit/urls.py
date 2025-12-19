from django.urls import path, include
from rest_framework.routers import DefaultRouter
from audit.views import AuditoriaViewSet

router = DefaultRouter()
router.register(r'auditoria', AuditoriaViewSet, basename='auditoria')

urlpatterns = [
    path('', include(router.urls)),
]

