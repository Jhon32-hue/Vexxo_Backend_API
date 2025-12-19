from django.contrib.auth import get_user_model, authenticate
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from users.serializers.user_serializer import UserSerializer

User = get_user_model()


class EmailOrUsernameTokenSerializer(TokenObtainPairSerializer):
    """
    Permite autenticación con 'username' o con 'email' en el mismo campo 'username'.
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        token["email"] = user.email
        return token

    def validate(self, attrs):
        login = attrs.get("username")  # DRF/JWT usa 'username' por defecto
        password = attrs.get("password")

        user = None
        # Primero intenta por username
        user = authenticate(username=login, password=password)
        # Si no, intenta por email
        if user is None:
            try:
                u = User.objects.get(email__iexact=login)
                user = authenticate(username=u.username, password=password)
            except User.DoesNotExist:
                pass

        if not user:
            raise self.fail("no_active_account")

        # Delega a la lógica base para generar tokens
        data = super().validate({"username": user.username, "password": password})
        # Marca actividad
        user.mark_seen(self.context.get("request"))
        return data


# ------------------- Registro -------------------
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]


# ------------------- Login (JWT) -------------------
class LoginView(TokenObtainPairView):
    serializer_class = EmailOrUsernameTokenSerializer


# ------------------- Perfil -------------------
class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        user = self.request.user
        user.mark_seen(self.request)
        return user


# ------------------- Logout -------------------
class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh = request.data["refresh"]
            token = RefreshToken(refresh)
            token.blacklist()
            return Response({"detail": "Sesión cerrada correctamente."}, status=status.HTTP_200_OK)
        except Exception:
            return Response({"error": "Token inválido o expirado."}, status=status.HTTP_400_BAD_REQUEST)
