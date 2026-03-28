"""
Rutas del bounded context de identidad.

Descripcion general:
- publica autenticacion, perfil, onboarding, dashboard y operaciones
  administrativas de `users`

Analisis detallado:
- la API de identidad se expone bajo `/api/identity/users/`
- tambien incluye endpoints de preparacion para OAuth social y contrato de
  eventos del contexto
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from identity.users.views.admin import UserAdminViewSet
from identity.users.views.auth import (
    CompleteOnboardingView,
    LoginView,
    LogoutView,
    ProfileView,
    RegisterView,
    SecureTokenRefreshView,
    SocialAuthExchangeView,
    SocialIdentityListView,
    SocialIdentityUnlinkView,
    SocialProviderCallbackView,
    SocialProviderStartView,
    SocialProvidersView,
    UserEventContractView,
)
from identity.users.views.dashboard import UserDashboardView

router = DefaultRouter()
router.register(r"admin/users", UserAdminViewSet, basename="admin-users")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="user-register"),
    path("auth/login/", LoginView.as_view(), name="user-login"),
    path("auth/refresh/", SecureTokenRefreshView.as_view(), name="user-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="user-logout"),
    path("auth/social/providers/", SocialProvidersView.as_view(), name="user-social-providers"),
    path("auth/social/exchange/", SocialAuthExchangeView.as_view(), name="user-social-exchange"),
    path("auth/social/<str:provider>/start/", SocialProviderStartView.as_view(), name="user-social-provider-start"),
    path("auth/social/<str:provider>/callback/", SocialProviderCallbackView.as_view(), name="user-social-provider-callback"),
    path("auth/social/identities/", SocialIdentityListView.as_view(), name="user-social-identities"),
    path("auth/social/<str:provider>/unlink/", SocialIdentityUnlinkView.as_view(), name="user-social-provider-unlink"),
    path("me/", ProfileView.as_view(), name="user-me"),
    path("onboarding/complete/", CompleteOnboardingView.as_view(), name="user-onboarding-complete"),
    path("dashboard/", UserDashboardView.as_view(), name="user-dashboard"),
    path("event-contract/", UserEventContractView.as_view(), name="user-event-contract"),
    path("", include(router.urls)),
]
