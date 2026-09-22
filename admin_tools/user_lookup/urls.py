from django.urls import include, path
from rest_framework.routers import DefaultRouter

from admin_tools.user_lookup.views import UserLookupViewSet


router = DefaultRouter()
router.register("users", UserLookupViewSet, basename="support-user")

urlpatterns = [path("", include(router.urls))]
