"""
API de consentimientos del usuario.

Descripcion general:
- expone CRUD y acciones operativas sobre consentimientos
- añade vistas resumidas para cumplimiento, open banking y soporte
"""

from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from identity.consents.models import UserConsent
from identity.consents.serializers import UserConsentGrantSerializer, UserConsentRevokeSerializer, UserConsentSerializer
from identity.consents.services import consent_summary_for_user, grant_consent, revoke_consent


class UserConsentViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "head", "options"]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserConsentSerializer

    def get_queryset(self):
        qs = UserConsent.objects.select_related("user").all()
        if self.request.user.is_staff or self.request.user.is_superuser:
            return qs
        return qs.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "grant":
            return UserConsentGrantSerializer
        if self.action == "revoke":
            return UserConsentRevokeSerializer
        return UserConsentSerializer

    def create(self, request, *args, **kwargs):
        serializer = UserConsentGrantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        consent = grant_consent(user=request.user, data=serializer.validated_data)
        return Response(UserConsentSerializer(consent, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["post"])
    def grant(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        consent = grant_consent(user=request.user, data=serializer.validated_data)
        return Response(UserConsentSerializer(consent, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        consent = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        revoke_consent(consent, reason=serializer.validated_data.get("revoke_reason", ""))
        return Response(UserConsentSerializer(consent, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["get"])
    def active(self, request):
        qs = self.get_queryset().filter(status="granted")
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = UserConsentSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)
        return Response(UserConsentSerializer(qs, many=True, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["get"])
    def expiring(self, request):
        qs = self.get_queryset().filter(status="granted", expires_at__isnull=False).order_by("expires_at")
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = UserConsentSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)
        return Response(UserConsentSerializer(qs, many=True, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        target_user = request.user
        if request.user.is_staff and request.query_params.get("user_id"):
            from django.contrib.auth import get_user_model

            target_user = get_user_model().objects.filter(pk=request.query_params.get("user_id")).first() or request.user
        return Response(consent_summary_for_user(target_user))
