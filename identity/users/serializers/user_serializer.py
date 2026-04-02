"""
Serializers del bounded context de identidad.

Descripcion general:
- define contratos de registro, perfil propio y administracion de usuarios
- alinea la API de `identity.users` con el lifecycle real de Vexxo

Analisis detallado:
- el frontend ya no debe enviar `username` para registrar usuarios; el sistema
  recibe nombre completo, correo y contrasena, y genera el username interno
- `User` sigue siendo el modelo base de autenticacion, pero la API de identidad
  debe hablar en terminos mas cercanos a producto: plan, onboarding, moneda
  preferida y estado
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.text import slugify
from rest_framework import serializers

from identity.users.domain.plan_matrix import resolve_plan_code
from identity.users.models.user import PlanType, UserStatus
from identity.users.services.product_access_service import get_user_usage_snapshot

User = get_user_model()


def _split_full_name(full_name: str) -> tuple[str, str]:
    normalized = " ".join((full_name or "").strip().split())
    if not normalized:
        return "", ""
    parts = normalized.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""
    return first_name, last_name


def _generate_username(*, email: str, full_name: str) -> str:
    base = slugify(full_name) or slugify(email.split("@", 1)[0]) or "usuario"
    candidate = base[:150] or "usuario"
    suffix = 1
    while User.objects.filter(username=candidate).exists():
        suffix += 1
        trimmed = base[: max(1, 150 - len(str(suffix)) - 1)] or "usuario"
        candidate = f"{trimmed}-{suffix}"
    return candidate


class BaseUserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="display_name", read_only=True)
    effective_plan = serializers.SerializerMethodField(read_only=True)
    plan_config = serializers.SerializerMethodField(read_only=True)

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
            "timezone_name",
            "locale",
            "whatsapp_connected",
            "photo",
            "plan",
            "effective_plan",
            "plan_config",
            "status",
            "is_verified",
            "is_premium",
            "is_active",
            "onboarding_completed",
            "last_seen",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "username",
            "plan",
            "plan_config",
            "status",
            "is_verified",
            "is_premium",
            "is_active",
            "whatsapp_connected",
            "last_seen",
            "created_at",
            "updated_at",
        ]

    def get_plan_config(self, obj):
        return obj.get_plan_config()

    def get_effective_plan(self, obj):
        return getattr(obj, "effective_plan", obj.plan)

    def validate_email(self, value):
        value = (value or "").strip().lower()
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Este correo ya esta registrado.")
        return value


class UserRegisterSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(write_only=True, required=True, max_length=150)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    preferred_currency = serializers.CharField(required=False, default="COP")
    timezone_name = serializers.CharField(required=False, default="America/Bogota")
    locale = serializers.CharField(required=False, default="es_CO")

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "password",
            "password2",
            "preferred_currency",
            "timezone_name",
            "locale",
            "phone_number",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Las contrasenas no coinciden."})
        if len(" ".join(attrs["full_name"].strip().split())) < 3:
            raise serializers.ValidationError({"full_name": "Debes enviar nombre completo."})
        return attrs

    def create(self, validated_data):
        full_name = validated_data.pop("full_name")
        validated_data.pop("password2")
        password = validated_data.pop("password")
        first_name, last_name = _split_full_name(full_name)
        email = validated_data["email"].strip().lower()

        user = User(
            username=_generate_username(email=email, full_name=full_name),
            email=email,
            first_name=first_name,
            last_name=last_name,
            preferred_currency=validated_data.get("preferred_currency", "COP"),
            timezone_name=validated_data.get("timezone_name", "America/Bogota"),
            locale=validated_data.get("locale", "es_CO"),
            phone_number=validated_data.get("phone_number", ""),
            plan=PlanType.FREE,
            is_active=True,
            status=UserStatus.ACTIVE,
        )
        user.set_password(password)
        user.save()
        return user

    def to_representation(self, instance):
        return BaseUserSerializer(instance, context=self.context).data


class UserMeSerializer(BaseUserSerializer):
    full_name = serializers.CharField(write_only=True, required=False)
    display_name = serializers.CharField(source="full_name", read_only=True)
    plan_usage = serializers.SerializerMethodField(read_only=True)

    class Meta(BaseUserSerializer.Meta):
        fields = BaseUserSerializer.Meta.fields + ["display_name", "plan_usage"]
        read_only_fields = BaseUserSerializer.Meta.read_only_fields + ["username", "plan"]

    def get_plan_usage(self, obj):
        return get_user_usage_snapshot(obj)

    def update(self, instance, validated_data):
        full_name = validated_data.pop("full_name", None)
        if full_name:
            first_name, last_name = _split_full_name(full_name)
            instance.first_name = first_name
            instance.last_name = last_name
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class UserAdminSerializer(BaseUserSerializer):
    max_accounts_override = serializers.IntegerField(required=False, allow_null=True)
    max_observed_accounts_override = serializers.IntegerField(required=False, allow_null=True)
    max_contacts_override = serializers.IntegerField(required=False, allow_null=True)
    max_api_connections_override = serializers.IntegerField(required=False, allow_null=True)
    max_monthly_reports_override = serializers.IntegerField(required=False, allow_null=True)

    class Meta(BaseUserSerializer.Meta):
        model = User
        fields = BaseUserSerializer.Meta.fields + [
            "max_accounts_override",
            "max_observed_accounts_override",
            "max_contacts_override",
            "max_api_connections_override",
            "max_monthly_reports_override",
            "is_staff",
            "is_superuser",
        ]
        read_only_fields = ["created_at", "updated_at", "last_seen"]

    def validate_plan(self, value):
        normalized = resolve_plan_code(value)
        if normalized not in {"free", "pro", "enterprise"}:
            raise serializers.ValidationError("Plan invalido.")
        return normalized
