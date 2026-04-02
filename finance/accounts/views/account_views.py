"""
ViewSet principal de cuentas financieras.

La clase publica se mantiene estable, pero la implementacion interna se divide
en query builders, helpers de auditoria y handlers de acciones.
"""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from finance.accounts.serializers import (
    AccountDetailSerializer,
    AccountExternalLinkSerializer,
    AccountPlanUsageSerializer,
    AccountReasonActionSerializer,
    AccountRecalcSerializer,
    AccountSyncErrorSerializer,
    AccountSyncRunningSerializer,
    AccountSyncScheduleSerializer,
    AccountSyncSuccessSerializer,
    AccountWriteSerializer,
)
from finance.accounts.views.account_action_handlers import AccountActionHandlersMixin
from finance.accounts.views.account_query_builders import (
    build_account_detail_queryset,
    build_account_list_queryset,
    build_account_mutation_queryset,
    build_account_overview_queryset,
)


class AccountViewSet(AccountActionHandlersMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AccountDetailSerializer

    def get_queryset(self):
        if self.action in {"list", "summary"}:
            return build_account_list_queryset(user=self.request.user, query_params=self.request.query_params)
        if self.action in {"retrieve", "members"}:
            return build_account_detail_queryset(user=self.request.user, query_params=self.request.query_params)
        if self.action in {"sync_overview", "operational_overview", "event_contract"}:
            return build_account_overview_queryset(user=self.request.user, query_params=self.request.query_params)
        return build_account_mutation_queryset(user=self.request.user, query_params=self.request.query_params)

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return AccountWriteSerializer
        if self.action == "link_external_source":
            return AccountExternalLinkSerializer
        if self.action == "mark_sync_running":
            return AccountSyncRunningSerializer
        if self.action == "mark_sync_success":
            return AccountSyncSuccessSerializer
        if self.action == "mark_sync_error":
            return AccountSyncErrorSerializer
        if self.action == "schedule_sync":
            return AccountSyncScheduleSerializer
        if self.action in {"freeze", "archive", "unarchive", "close_account"}:
            return AccountReasonActionSerializer
        if self.action == "recalc_balance":
            return AccountRecalcSerializer
        if self.action == "plan_usage":
            return AccountPlanUsageSerializer
        return AccountDetailSerializer
