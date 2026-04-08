"""
ViewSets de inteligencia derivada para accounts.

Descripcion general:
- exponen snapshots y read models derivados del modulo de cuentas
- permiten consultar el perfil financiero base del usuario sin recalcularlo en
  cada request

Analisis detallado:
- esta API no reemplaza `cuentas`; la complementa con lecturas agregadas y
  explicables
- el endpoint de refresh permite recalcular por demanda las proyecciones cuando
  soporte, producto o el propio usuario necesitan forzar consistencia
- `worker_report` deja un callback explicito para materializadores externos que
  necesitan cerrar o fallar corridas sin depender del refresh inline
"""

from __future__ import annotations

import logging

from django.conf import settings
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from finance.accounts.models import (
    AccountCurrencyExposure,
    AccountOwnerMetrics,
    AccountPortfolioSnapshot,
    AccountProductSignal,
    AccountRiskSnapshot,
    AccountTypeDistribution,
)
from finance.accounts.serializers.intelligence_serializers import (
    AccountCurrencyExposureSerializer,
    AccountIntelligenceRefreshSerializer,
    AccountIntelligenceWorkerReportSerializer,
    AccountOwnerMetricsSerializer,
    AccountPortfolioSnapshotSerializer,
    AccountProductSignalSerializer,
    AccountRiskSnapshotSerializer,
    AccountTypeDistributionSerializer,
)
from finance.accounts.services.intelligence_dispatch_service import (
    account_intelligence_local_fallback_allowed,
    enqueue_account_intelligence_refresh_task,
    get_account_intelligence_projection_status,
    report_account_intelligence_worker_status,
)
from finance.accounts.services.intelligence_health_service import get_account_intelligence_operational_health
from finance.accounts.services.intelligence_service import refresh_account_intelligence_for_user

logger = logging.getLogger(__name__)


class _ReadOnlyIntelligenceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if getattr(self, "action", "") == "worker_report":
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user)


class AccountPortfolioSnapshotViewSet(_ReadOnlyIntelligenceViewSet):
    queryset = AccountPortfolioSnapshot.objects.select_related("owner", "primary_account")
    serializer_class = AccountPortfolioSnapshotSerializer

    def _assert_internal_worker_token(self, request) -> None:
        expected = str(getattr(settings, "ACCOUNTS_INTELLIGENCE_INTERNAL_TOKEN", "") or "").strip()
        if not expected:
            raise PermissionDenied("El token interno de inteligencia no esta configurado.")
        provided = str(request.headers.get("X-Vexxo-Internal-Token", "") or "").strip()
        if provided != expected:
            raise PermissionDenied("Token interno invalido.")

    @action(detail=False, methods=["post"])
    def refresh(self, request):
        serializer = AccountIntelligenceRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        task_response = enqueue_account_intelligence_refresh_task(
            owner_id=request.user.pk,
            source="accounts.intelligence_views.refresh",
            task_name_suffix=f"manual-refresh-{request.user.pk}",
        )
        if not account_intelligence_local_fallback_allowed():
            if task_response is None:
                logger.warning(
                    "[accounts.intelligence] Refresh requested without async dispatch owner_id=%s",
                    request.user.pk,
                )
            return Response(
                {
                    "detail": "Refresh de inteligencia agendado.",
                    "queued": bool(task_response is not None),
                    "projection_status": get_account_intelligence_projection_status(owner=request.user),
                    "projection_health": get_account_intelligence_operational_health(
                        owner=request.user,
                        sync_alerts=True,
                    ),
                },
                status=status.HTTP_202_ACCEPTED,
            )

        result = refresh_account_intelligence_for_user(request.user)
        payload = {
            "portfolio_snapshot": AccountPortfolioSnapshotSerializer(
                result["portfolio_snapshot"],
                context=self.get_serializer_context(),
            ).data,
            "risk_snapshot": AccountRiskSnapshotSerializer(
                result["risk_snapshot"],
                context=self.get_serializer_context(),
            ).data,
            "product_signals": AccountProductSignalSerializer(
                result["product_signals"],
                many=True,
                context=self.get_serializer_context(),
            ).data,
            "owner_metrics": AccountOwnerMetricsSerializer(
                result["owner_metrics"],
                context=self.get_serializer_context(),
            ).data,
            "currency_exposures": AccountCurrencyExposureSerializer(
                result["currency_exposures"],
                many=True,
                context=self.get_serializer_context(),
            ).data,
            "type_distributions": AccountTypeDistributionSerializer(
                result["type_distributions"],
                many=True,
                context=self.get_serializer_context(),
            ).data,
            "projection_health": get_account_intelligence_operational_health(
                owner=request.user,
                sync_alerts=True,
            ),
        }
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def overview(self, request):
        projection_status = get_account_intelligence_projection_status(owner=request.user)
        projection_health = get_account_intelligence_operational_health(
            owner=request.user,
            sync_alerts=True,
        )
        if not account_intelligence_local_fallback_allowed():
            if projection_status["pending"] and not projection_status["cloud_tasks_ready"]:
                logger.warning(
                    "[accounts.intelligence] Overview pending without materialized projections owner_id=%s",
                    request.user.pk,
                )
            portfolio = self.get_queryset().order_by("-snapshot_at").first()
            risk = AccountRiskSnapshot.objects.filter(owner=request.user).order_by("-generated_at").first()
            signals = list(AccountProductSignal.objects.filter(owner=request.user, is_active=True).order_by("signal_code"))
            owner_metrics = AccountOwnerMetrics.objects.filter(owner=request.user).order_by("-generated_at").first()
            exposures = list(AccountCurrencyExposure.objects.filter(owner=request.user).order_by("currency"))
            distributions = list(AccountTypeDistribution.objects.filter(owner=request.user).order_by("account_type"))
            return Response(
                {
                    "portfolio_snapshot": AccountPortfolioSnapshotSerializer(portfolio).data if portfolio else None,
                    "risk_snapshot": AccountRiskSnapshotSerializer(risk).data if risk else None,
                    "product_signals": AccountProductSignalSerializer(signals, many=True).data,
                    "owner_metrics": AccountOwnerMetricsSerializer(owner_metrics).data if owner_metrics else None,
                    "currency_exposures": AccountCurrencyExposureSerializer(exposures, many=True).data,
                    "type_distributions": AccountTypeDistributionSerializer(distributions, many=True).data,
                    "projection_pending": projection_status["pending"],
                    "projection_status": projection_status,
                    "projection_health": projection_health,
                },
                status=status.HTTP_200_OK,
            )
        result = refresh_account_intelligence_for_user(request.user)
        payload = {
            "portfolio_snapshot": AccountPortfolioSnapshotSerializer(result["portfolio_snapshot"]).data,
            "risk_snapshot": AccountRiskSnapshotSerializer(result["risk_snapshot"]).data,
            "product_signals": AccountProductSignalSerializer(result["product_signals"], many=True).data,
            "owner_metrics": AccountOwnerMetricsSerializer(result["owner_metrics"]).data,
            "currency_exposures": AccountCurrencyExposureSerializer(result["currency_exposures"], many=True).data,
            "type_distributions": AccountTypeDistributionSerializer(result["type_distributions"], many=True).data,
            "projection_status": get_account_intelligence_projection_status(owner=request.user),
            "projection_health": projection_health,
        }
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def health(self, request):
        return Response(
            {
                "user_id": str(request.user.pk),
                "projection_status": get_account_intelligence_projection_status(owner=request.user),
                "projection_health": get_account_intelligence_operational_health(
                    owner=request.user,
                    sync_alerts=True,
                ),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], permission_classes=[AllowAny], url_path="worker-report")
    def worker_report(self, request):
        self._assert_internal_worker_token(request)
        serializer = AccountIntelligenceWorkerReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report = report_account_intelligence_worker_status(
            owner_id=serializer.validated_data["owner_id"],
            status=serializer.validated_data["status"],
            task_name=serializer.validated_data.get("task_name", ""),
            result=serializer.validated_data.get("result", ""),
            error_message=serializer.validated_data.get("error_message", ""),
        )
        return Response(report, status=status.HTTP_200_OK if report.get("applied") else status.HTTP_202_ACCEPTED)


class AccountRiskSnapshotViewSet(_ReadOnlyIntelligenceViewSet):
    queryset = AccountRiskSnapshot.objects.select_related("owner")
    serializer_class = AccountRiskSnapshotSerializer


class AccountProductSignalViewSet(_ReadOnlyIntelligenceViewSet):
    queryset = AccountProductSignal.objects.select_related("owner").order_by("signal_code")
    serializer_class = AccountProductSignalSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        active = self.request.query_params.get("active")
        if active is not None:
            active_value = (active or "").strip().lower() in {"1", "true", "yes", "si"}
            qs = qs.filter(is_active=active_value)
        return qs


class AccountOwnerMetricsViewSet(_ReadOnlyIntelligenceViewSet):
    queryset = AccountOwnerMetrics.objects.select_related("owner")
    serializer_class = AccountOwnerMetricsSerializer


class AccountCurrencyExposureViewSet(_ReadOnlyIntelligenceViewSet):
    queryset = AccountCurrencyExposure.objects.select_related("owner").order_by("currency")
    serializer_class = AccountCurrencyExposureSerializer


class AccountTypeDistributionViewSet(_ReadOnlyIntelligenceViewSet):
    queryset = AccountTypeDistribution.objects.select_related("owner").order_by("account_type")
    serializer_class = AccountTypeDistributionSerializer
