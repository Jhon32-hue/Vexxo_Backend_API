from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    full_name = serializers.SerializerMethodField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id","username","email","first_name","last_name",
            "full_name","phone_number","preferred_currency",
            "whatsapp_connected","photo",
            "is_verified","is_premium","is_active",
            "password","password2","created_at","updated_at",
        ]
        read_only_fields = ["is_verified","is_premium","whatsapp_connected","created_at","updated_at"]

    def get_full_name(self, obj):
        return obj.full_name()

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Este correo ya está registrado.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Las contraseñas no coinciden."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user
