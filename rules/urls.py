from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rules.views import ReglaViewSet

router = DefaultRouter()
router.register(r'reglas', ReglaViewSet, basename='regla')

urlpatterns = [
    path('', include(router.urls)),
]

