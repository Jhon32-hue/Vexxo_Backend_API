from rest_framework import serializers
from audit.models.audit import AuditLog


class AuditoriaSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    timestamp = serializers.DateTimeField(source="ts", read_only=True)
    is_automated = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "user_id",
            "module",
            "action",
            "source",
            "impact",
            "entity",
            "entity_id",
            "description",
            "diff",
            "metadata",
            "is_automated",
            "timestamp",
        ]
        read_only_fields = fields

    def get_is_automated(self, obj):
        return obj.source in {"SYSTEM", "AI", "AUTOMATION"}
