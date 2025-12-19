from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


class WebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        # Verificación básica (placeholder)
        return Response({"ok": True, "msg": "whatsapp webhook verify"}, status=status.HTTP_200_OK)

    def post(self, request):
        # Recibir eventos (placeholder)
        return Response({"ok": True, "event": request.data}, status=status.HTTP_200_OK)

