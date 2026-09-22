from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

User = get_user_model()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    redirect_url = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_email(self, value):
        return (value or "").strip().lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)
    mfa_code = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=32)

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Las contrasenas no coinciden."})
        user = self._resolve_user(attrs["uid"])
        if user is None:
            raise serializers.ValidationError({"uid": "Solicitud invalida o expirada."})
        if not PasswordResetTokenGenerator().check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "Solicitud invalida o expirada."})
        from identity.users.services.mfa_service import get_active_mfa_method, verify_mfa_code

        if get_active_mfa_method(user) is not None:
            verified, _method = verify_mfa_code(user=user, code=attrs.get("mfa_code", ""))
            if not verified:
                raise serializers.ValidationError({"mfa_code": "Se requiere un segundo factor valido."})
        attrs["user"] = user
        return attrs

    @staticmethod
    def _resolve_user(uid: str):
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
        except Exception:
            return None
        return User.objects.filter(pk=user_id, is_active=True).first()


class SetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError({"new_password": "Las contrasenas no coinciden."})
        return attrs


class PasswordRecoveryCodeRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=32)


class PasswordRecoveryCodeConfirmSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=32)
    code = serializers.CharField(max_length=12)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)
    mfa_code = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=32)

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Las contrasenas no coinciden."})
        return attrs


class StepUpCodeRequestSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(required=False, allow_null=True)


class StepUpCodeConfirmSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(required=False, allow_null=True)
    code = serializers.CharField(max_length=12)


class MfaTotpEnrollSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, max_length=256)


class MfaCodeSerializer(serializers.Serializer):
    code = serializers.CharField(write_only=True, min_length=6, max_length=32)
    session_id = serializers.IntegerField(required=False, allow_null=True)


class MfaDisableSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, max_length=256)
