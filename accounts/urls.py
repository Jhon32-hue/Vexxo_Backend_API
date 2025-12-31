from django.urls import path, include
from rest_framework.routers import DefaultRouter
from accounts.views.account_views import AccountViewSet

router = DefaultRouter()
router.register(r"cuentas", AccountViewSet, basename="cuentas")

urlpatterns = [
    path("", include(router.urls)),
]
