from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.internal_auth import assert_internal_token
from finance.accounts.models import Account
from finance.accounts.serializers import (
    AccountDetailSerializer,
    AccountSyncErrorSerializer,
    AccountSyncRunningSerializer,
    AccountSyncSuccessSerializer,
)
from finance.accounts.services.account_sync_service import (
    mark_account_sync_error,
    mark_account_sync_running,
    mark_account_sync_stale,
    mark_account_sync_success,
)


class InternalAccountSyncStatusView(APIView):
    permission_classes = [permissions.AllowAny]

    def _get_account(self, account_id: int) -> Account | None:
        return Account.objects.filter(pk=account_id).first()

    def _serialize_account(self, account: Account, request) -> Response:
        return Response(
            AccountDetailSerializer(account, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request, account_id: int, sync_status: str):
        try:
            assert_internal_token(
                request,
                "ACCOUNTS_SYNC_INTERNAL_TOKEN",
                detail="No autorizado para sync interno.",
            )
        except Exception as exc:
            return Response({"detail": str(getattr(exc, "detail", exc))}, status=status.HTTP_403_FORBIDDEN)

        account = self._get_account(account_id)
        if account is None:
            return Response({"detail": "Cuenta no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        if not account.has_external_link:
            return Response({"detail": "La cuenta no esta vinculada a un proveedor externo."}, status=status.HTTP_400_BAD_REQUEST)

        if sync_status == "running":
            serializer = AccountSyncRunningSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            mark_account_sync_running(account=account, data=serializer.validated_data)
            return self._serialize_account(account, request)

        if sync_status == "success":
            serializer = AccountSyncSuccessSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            mark_account_sync_success(account=account, data=serializer.validated_data)
            return self._serialize_account(account, request)

        if sync_status == "error":
            serializer = AccountSyncErrorSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            mark_account_sync_error(account=account, data=serializer.validated_data)
            return self._serialize_account(account, request)

        if sync_status == "stale":
            mark_account_sync_stale(account)
            return self._serialize_account(account, request)

        return Response({"detail": "Estado de sync interno no soportado."}, status=status.HTTP_400_BAD_REQUEST)
