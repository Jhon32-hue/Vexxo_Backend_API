from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.internal_auth import assert_internal_token
from integrations_stub.llm.services import process_stub_transaction_inference_request


class InternalTransactionInferenceWorkerSerializer(serializers.Serializer):
    inference_request_id = serializers.UUIDField()
    request_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
    source = serializers.CharField(required=False, allow_blank=True, max_length=128)


class InternalTransactionInferenceWorkerView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            assert_internal_token(
                request,
                "TRANSACTION_INFERENCE_INTERNAL_TOKEN",
                detail="No autorizado para worker interno de inferencia transaccional.",
            )
        except Exception:
            return Response(
                {"detail": "No autorizado para worker interno de inferencia transaccional."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = InternalTransactionInferenceWorkerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = process_stub_transaction_inference_request(**serializer.validated_data)
        if result.get("result") == "missing_inference_request":
            return Response({"detail": "Solicitud de inferencia no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        return Response(result, status=status.HTTP_200_OK)
