from io import BytesIO

from django.http import FileResponse
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.files.models import DocumentFile
from documents.files.serializers import (
    DocumentFileSerializer,
    DocumentUploadSerializer,
    OcrRequestCreateSerializer,
    OcrFieldCorrectionSerializer,
    OcrFieldObservationSerializer,
    OcrRequestSummarySerializer,
)
from documents.files.services import consume_download_grant, issue_download_grant, soft_delete_document, store_document
from documents.ocr_requests.models import OcrRequest
from documents.ocr_requests.services import correct_ocr_field, request_ocr


class DocumentFileViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = DocumentFileSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return DocumentFile.objects.filter(owner=self.request.user, deleted_at__isnull=True).prefetch_related("ocr_requests")

    def list(self, request):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    def retrieve(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)

    def create(self, request):
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        document = store_document(
            owner=request.user,
            uploaded_file=data["file"],
            expected_sha256=data.get("sha256", ""),
            metadata={
                "capture_source": data.get("capture_source", "upload"),
                "merchant_hint": data.get("merchant_hint", ""),
                "amount_hint": data.get("amount_hint"),
                "currency_hint": data.get("currency_hint", ""),
            },
        )
        response_status = status.HTTP_200_OK if document._idempotent_replay else status.HTTP_201_CREATED
        return Response(self.get_serializer(document).data, status=response_status)

    def destroy(self, request, pk=None):
        soft_delete_document(document=self.get_object(), owner=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="request-ocr")
    def request_ocr(self, request, pk=None):
        serializer = OcrRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ocr = request_ocr(
            owner=request.user,
            document=self.get_object(),
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            **serializer.validated_data,
        )
        response_status = status.HTTP_200_OK if ocr._idempotent_replay else status.HTTP_202_ACCEPTED
        return Response(OcrRequestSummarySerializer(ocr).data, status=response_status)

    @action(detail=True, methods=["post"], url_path="download-grant")
    def download_grant(self, request, pk=None):
        grant, token = issue_download_grant(document=self.get_object(), owner=request.user)
        return Response({
            "grant_id": str(grant.pk),
            "token": token,
            "expires_at": grant.expires_at,
            "download_path": f"/api/documents/downloads/{grant.pk}/",
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="ocr-corrections")
    def correct_ocr(self, request, pk=None):
        document = self.get_object()
        serializer = OcrFieldCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ocr_request = OcrRequest.objects.filter(
            pk=data["ocr_request"],
            document=document,
            owner=request.user,
        ).first()
        if ocr_request is None:
            return Response({"detail": "Solicitud OCR no disponible."}, status=status.HTTP_404_NOT_FOUND)
        observation = correct_ocr_field(
            request=ocr_request,
            owner=request.user,
            field_name=data["field_name"],
            value=data["value"],
            notes=data["notes"],
        )
        return Response(OcrFieldObservationSerializer(observation).data, status=status.HTTP_201_CREATED)


class DocumentDownloadView(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def retrieve(self, request, pk=None):
        try:
            grant, content = consume_download_grant(
                grant_id=pk,
                raw_token=request.headers.get("X-Download-Token", ""),
            )
        except Exception:
            return Response({"detail": "Grant invalido, usado o expirado."}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(BytesIO(content), content_type=grant.document.content_type or "application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{grant.document.original_name}"'
        response["Cache-Control"] = "no-store"
        return response
