from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from users.views.auth import RegisterView, LoginView, ProfileView, LogoutView
from users.views.dashboard import UserDashboardView

urlpatterns = [
    path("registro/", RegisterView.as_view(), name="registro"),
    path("login/", LoginView.as_view(), name="login"),
    path("perfil/", ProfileView.as_view(), name="perfil"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("resumen/", UserDashboardView.as_view(), name="resumen"),

]
