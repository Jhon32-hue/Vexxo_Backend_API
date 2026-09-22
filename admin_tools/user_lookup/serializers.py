from rest_framework import serializers


class SupportUserSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    display_name = serializers.CharField()
    plan = serializers.CharField()
    status = serializers.CharField()
    is_active = serializers.BooleanField()
    is_verified = serializers.BooleanField()
    onboarding_completed = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    last_seen = serializers.DateTimeField(allow_null=True)


class SupportUserOverviewSerializer(serializers.Serializer):
    identity = serializers.DictField()
    security = serializers.DictField()
    finance = serializers.DictField()
    operations = serializers.DictField()
