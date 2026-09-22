from rest_framework import serializers

from documents.files.models import DocumentFile
from documents.metadata.models import DocumentMetadata
from documents.ocr_requests.models import OcrFieldObservation, OcrRequest


class DocumentMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentMetadata
        exclude = ["id", "document"]


class OcrRequestSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = OcrRequest
        fields = ["id", "status", "engine", "attempt_count", "last_error", "created_at", "completed_at"]


class DocumentFileSerializer(serializers.ModelSerializer):
    metadata = DocumentMetadataSerializer(source="document_metadata", read_only=True)
    latest_ocr = serializers.SerializerMethodField()

    class Meta:
        model = DocumentFile
        fields = [
            "id", "original_name", "content_type", "size_bytes", "sha256", "status",
            "is_encrypted", "scan_status", "scan_engine", "scanned_at",
            "metadata", "latest_ocr", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_latest_ocr(self, obj):
        request = obj.ocr_requests.order_by("-created_at").first()
        return OcrRequestSummarySerializer(request).data if request else None


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    sha256 = serializers.RegexField(r"^[a-fA-F0-9]{64}$", required=False, allow_blank=True)
    capture_source = serializers.CharField(max_length=32, required=False, default="upload")
    merchant_hint = serializers.CharField(max_length=180, required=False, allow_blank=True, default="")
    amount_hint = serializers.DecimalField(max_digits=20, decimal_places=2, required=False, allow_null=True)
    currency_hint = serializers.CharField(max_length=12, required=False, allow_blank=True, default="")


class OcrRequestCreateSerializer(serializers.Serializer):
    client_extracted_text = serializers.CharField(required=False, allow_blank=True, max_length=100000)
    client_structured_hint = serializers.JSONField(required=False)

    def validate_client_structured_hint(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Debe ser un objeto JSON.")
        return value


class OcrFieldCorrectionSerializer(serializers.Serializer):
    ocr_request = serializers.UUIDField()
    field_name = serializers.RegexField(r"^[A-Za-z][A-Za-z0-9_.-]{0,95}$")
    value = serializers.JSONField()
    notes = serializers.CharField(min_length=5, max_length=255)


class OcrFieldObservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = OcrFieldObservation
        fields = (
            "id",
            "request",
            "field_name",
            "normalized_value",
            "confidence_score",
            "source",
            "extractor_version",
            "schema_version",
            "supersedes",
            "corrected_by",
            "correction_reason",
            "created_at",
        )
        read_only_fields = fields
