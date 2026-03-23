from django.urls import path, include
from rest_framework.routers import DefaultRouter
from planning.goals.views import MetaViewSet

router = DefaultRouter()
router.register(r'metas', MetaViewSet, basename='meta')

urlpatterns = [
    path('', include(router.urls)),
]
