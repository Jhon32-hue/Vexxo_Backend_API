"""
API de dispositivos del usuario.

Descripcion general:
- expone CRUD, registro y operaciones de confianza sobre dispositivos
- agrega endpoints de resumen para observabilidad operacional del usuario

Analisis detallado:
- la UI y soporte necesitan listar dispositivos, marcarlos confiables o
  revocarlos sin mezclar esa logica con el login directo
- el resumen entrega una vista compacta de seguridad del usuario y reduce
  queries repetidas en dashboards o paneles administrativos
"""

from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from identity.devices.models import UserDevice
from identity.devices.serializers import UserDeviceRegisterSerializer, UserDeviceSerializer, UserDeviceTrustSerializer
from identity.devices.services import device_summary_for_user, register_or_update_device, revoke_device, trust_device
from identity.users.views.permissions import IsAdminUser


class UserDeviceViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "head", "options"]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserDeviceSerializer

    def get_queryset(self):
        qs = UserDevice.objects.select_related("user").all()
        if self.request.user.is_staff or self.request.user.is_superuser:
            return qs
        return qs.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "register_device":
            return UserDeviceRegisterSerializer
        if self.action == "trust_device":
            return UserDeviceTrustSerializer
        return UserDeviceSerializer

    def create(self, request, *args, **kwargs):
        serializer = UserDeviceRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = register_or_update_device(user=request.user, request=request, payload=serializer.validated_data)
        return Response(UserDeviceSerializer(device, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["post"])
    def register_device(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = register_or_update_device(user=request.user, request=request, payload=serializer.validated_data)
        return Response(UserDeviceSerializer(device, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def trust_device(self, request, pk=None):
        device = self.get_object()
        if not (request.user == device.user or request.user.is_staff or request.user.is_superuser):
            self.permission_denied(request, message="No puedes modificar este dispositivo.")
        trust_device(device)
        return Response(UserDeviceSerializer(device, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        device = self.get_object()
        if not (request.user == device.user or request.user.is_staff or request.user.is_superuser):
            self.permission_denied(request, message="No puedes revocar este dispositivo.")
        revoke_device(device)
        return Response(UserDeviceSerializer(device, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated, IsAdminUser])
    def suspicious(self, request):
        qs = self.get_queryset().filter(trust_level="suspicious", is_active=True)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = UserDeviceSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)
        return Response(UserDeviceSerializer(qs, many=True, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        target_user = request.user
        if request.user.is_staff and request.query_params.get("user_id"):
            from django.contrib.auth import get_user_model

            target_user = get_user_model().objects.filter(pk=request.query_params.get("user_id")).first() or request.user
        return Response(device_summary_for_user(target_user))
