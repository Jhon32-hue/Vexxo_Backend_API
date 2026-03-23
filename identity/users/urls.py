# users/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from identity.users.views.auth import RegisterView, LoginView, LogoutView, ProfileView
from identity.users.views.dashboard import UserDashboardView
from identity.users.views.admin import UserAdminViewSet

router = DefaultRouter()
router.register(r"admin/users", UserAdminViewSet, basename="admin-users")

urlpatterns = [
    # Auth
    path("auth/register/", RegisterView.as_view(), name="user-register"),
    path("auth/login/", LoginView.as_view(), name="user-login"),
    path("auth/logout/", LogoutView.as_view(), name="user-logout"),
    path("me/", ProfileView.as_view(), name="user-me"),
    # Dashboard
    path("dashboard/", UserDashboardView.as_view(), name="user-dashboard"),
    # Admin router
    path("", include(router.urls)),
]
