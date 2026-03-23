# users/views/auth.py
from django.contrib.auth import get_user_model, authenticate
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from identity.users.serializers.user_serializer import (
    UserRegisterSerializer,
    UserMeSerializer,
)
from identity.users.models.user import PlanType

User = get_user_model()


class EmailOrUsernameTokenSerializer(TokenObtainPairSerializer):
    """
    Autenticación con username o email en el mismo campo 'username'.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Extra claims
        token["username"] = user.username
        token["email"] = user.email
        token["plan"] = user.plan
        token["base_currency"] = user.base_currency
        return token

    def validate(self, attrs):
        login = attrs.get("username")
        password = attrs.get("password")

        user = authenticate(username=login, password=password)

        if user is None:
            try:
                u = User.objects.get(email__iexact=login)
                user = authenticate(username=u.username, password=password)
            except User.DoesNotExist:
                pass

        if not user:
            raise self.fail("no_active_account")

        data = super().validate({"username": user.username, "password": password})
        user.mark_seen(self.context.get("request"))
        return data


class RegisterView(generics.CreateAPIView):
    """
    Registro de nuevos usuarios (plan FREE por defecto).
    """
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
    serializer_class = EmailOrUsernameTokenSerializer


class ProfileView(generics.RetrieveUpdateAPIView):
    """
    Perfil del usuario autenticado (/api/users/me/).
    """
    serializer_class = UserMeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        user = self.request.user
        user.mark_seen(self.request)
        return user


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        Logout invalidando el refresh token.
        """
        refresh = request.data.get("refresh")
        if not refresh:
            return Response(
                {"error": "Falta el token de refresh."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh)
            token.blacklist()
            return Response(
                {"detail": "Sesión cerrada correctamente."},
                status=status.HTTP_200_OK,
            )
        except Exception:
            return Response(
                {"error": "Token inválido o expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
