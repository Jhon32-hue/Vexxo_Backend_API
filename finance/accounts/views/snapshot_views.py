"""
ViewSet de snapshots de reconciliacion de balances.

Descripcion general:
- expone lectura de snapshots historicos y creacion manual via servicio
  `create_balance_snapshot`

Analisis detallado:
- esta API sirve para soporte, auditoria operativa y jobs manuales de salud
  financiera sobre el modulo accounts
- los usuarios con acceso de lectura a una cuenta pueden ver sus snapshots
- la creacion manual con o sin `auto_repair` queda reservada a quien puede
  administrar la configuracion de la cuenta

Que se puede hacer despues:
- agregar acciones de reconciliacion mas profundas con evidencia por transaccion
- emitir alertas cuando el drift exceda umbrales por tipo de cuenta
"""

from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from finance.accounts.models import BalanceSnapshot
from finance.accounts.serializers import BalanceSnapshotCreateSerializer, BalanceSnapshotSerializer
from finance.accounts.services.permission_service import account_scope_for_user, user_can_manage_account_settings
from support.audit.helpers import audit_log


class BalanceSnapshotViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    API de reconciliacion y observabilidad de balances.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BalanceSnapshotSerializer

    def get_queryset(self):
        from finance.accounts.models import Account

        scoped_accounts = account_scope_for_user(self.request.user, Account.objects.all())
        qs = BalanceSnapshot.objects.select_related("account").filter(account__in=scoped_accounts)

        account_id = self.request.query_params.get("account")
        is_consistent = self.request.query_params.get("is_consistent")
        source = self.request.query_params.get("source")

        if account_id:
            qs = qs.filter(account_id=account_id)
        if is_consistent is not None:
            qs = qs.filter(is_consistent=(is_consistent or "").strip().lower() in {"1", "true", "yes", "si"})
        if source:
            qs = qs.filter(source=source)

        return qs.order_by("-as_of", "-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return BalanceSnapshotCreateSerializer
        return BalanceSnapshotSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        account = serializer.validated_data["account"]
        if not user_can_manage_account_settings(request.user, account):
            raise PermissionDenied("No puedes reconciliar esta cuenta.")

        snapshot = serializer.save()
        audit_log(
            user=request.user,
            module="accounts",
            action="balance_snapshot_create",
            entity="BalanceSnapshot",
            entity_id=snapshot.id,
            description=f"Snapshot manual de balance para cuenta {snapshot.account_id}",
            metadata={
                "account_id": snapshot.account_id,
                "source": snapshot.source,
                "is_consistent": snapshot.is_consistent,
                "drift": str(snapshot.drift),
            },
            silent=True,
        )

        output = BalanceSnapshotSerializer(snapshot, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def latest(self, request):
        account_id = request.query_params.get("account")
        if not account_id:
            return Response({"detail": "Debes enviar ?account=<id>."}, status=status.HTTP_400_BAD_REQUEST)

        snapshot = self.get_queryset().filter(account_id=account_id).first()
        if not snapshot:
            return Response({"detail": "No hay snapshots para esa cuenta."}, status=status.HTTP_404_NOT_FOUND)

        serializer = BalanceSnapshotSerializer(snapshot, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)
