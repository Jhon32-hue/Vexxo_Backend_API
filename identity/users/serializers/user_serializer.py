# users/serializers/user_serializer.py
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from identity.users.models.user import PlanType  # si el modelo está en este mismo módulo

User = get_user_model()


class BaseUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "preferred_currency",
            "whatsapp_connected",
            "photo",
            "plan",
            "is_verified",
            "is_premium",
            "is_active",
            "last_seen",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "plan",
            "is_verified",
            "is_premium",
            "is_active",
            "whatsapp_connected",
            "last_seen",
            "created_at",
            "updated_at",
        ]

    def get_full_name(self, obj):
        return obj.full_name()

    def validate_email(self, value):
        # En create: no repetir email. En update: permitir mismo email.
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Este correo ya está registrado.")
        return value


class UserRegisterSerializer(BaseUserSerializer):
    """
    Serializador para registro.
    """

    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta(BaseUserSerializer.Meta):
        fields = BaseUserSerializer.Meta.fields + [
            "password",
            "password2",
        ]
        # plan lo definimos siempre como FREE al registrar
        read_only_fields = BaseUserSerializer.Meta.read_only_fields + ["plan"]

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password": "Las contraseñas no coinciden."}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")
        password = validated_data.pop("password")
        # Siempre plan FREE al inicio
        user = User(**validated_data)
        user.set_password(password)
        user.plan = PlanType.FREE
        user.is_active = True
        user.save()
        return user


class UserMeSerializer(BaseUserSerializer):
    """
    Perfil del propio usuario (GET/PUT/PATCH /me).
    Solo permite cambiar datos básicos, no plan ni flags.
    """

    class Meta(BaseUserSerializer.Meta):
        read_only_fields = BaseUserSerializer.Meta.read_only_fields + [
            "username",
            "plan",
        ]


class UserAdminSerializer(BaseUserSerializer):
    """
    Para admins / superadmins, con control completo de plan y overrides.
    """

    max_accounts_override = serializers.IntegerField(
        required=False, allow_null=True
    )
    max_observed_accounts_override = serializers.IntegerField(
        required=False, allow_null=True
    )

    class Meta(BaseUserSerializer.Meta):
        model = User
        fields = BaseUserSerializer.Meta.fields + [
            "max_accounts_override",
            "max_observed_accounts_override",
            "is_staff",
            "is_superuser",
        ]
        read_only_fields = [
            "last_seen",
            "created_at",
            "updated_at",
        ]

    def validate_plan(self, value):
        if value not in [p.value for p in PlanType]:
            raise serializers.ValidationError("Plan inválido.")
        return value
