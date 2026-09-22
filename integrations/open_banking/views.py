import hashlib

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.open_banking.adapters import OpenBankingProviderError, get_open_banking_adapter
from integrations.open_banking.models import OpenBankingConnection, OpenBankingInstitution
from integrations.open_banking.provider_catalog import get_provider, list_providers
from integrations.open_banking.security import verify_webhook_signature
from integrations.open_banking.serializers import (
    ImportOpenBankingAccountSerializer,
    OpenBankingConnectionSerializer,
    OpenBankingInstitutionSerializer,
    OpenBankingTimelineEventSerializer,
    OpenBankingWebhookSerializer,
)
from integrations.open_banking.lifecycle import refresh_connection_credentials, reconcile_connection_account
from integrations.open_banking.services import (
    materialize_provider_account,
    process_provider_webhook,
    request_connection_sync,
    revoke_open_banking_connection,
)
from security.audit import record_security_event
from security.models import SecurityAuditEvent
from security.rate_limits import consume_rate_limit


class OpenBankingProviderListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({"results": list_providers()})


class OpenBankingInstitutionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = OpenBankingInstitution.objects.filter(is_active=True)
        country = str(request.query_params.get("country") or "").upper()[:2]
        if country:
            queryset = queryset.filter(country=country)
        return Response({"results": OpenBankingInstitutionSerializer(queryset, many=True).data})


class OpenBankingConnectionViewSet(viewsets.ModelViewSet):
    serializer_class = OpenBankingConnectionSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "public_id"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return (
            OpenBankingConnection.objects.filter(owner=self.request.user)
            .select_related("consent")
            .prefetch_related("account_links__account")
        )

    @action(detail=True, methods=["post"])
    def revoke(self, request, public_id=None):
        connection = revoke_open_banking_connection(self.get_object())
        return Response(self.get_serializer(connection).data)

    @action(detail=True, methods=["post"], url_path="request-sync")
    def request_sync(self, request, public_id=None):
        connection = request_connection_sync(self.get_object())
        return Response(self.get_serializer(connection).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="import-account")
    def import_account(self, request, public_id=None):
        serializer = ImportOpenBankingAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        materialize_provider_account(
            connection=self.get_object(),
            external_account_id=serializer.validated_data["external_account_id"],
        )
        connection = self.get_queryset().get(public_id=public_id)
        return Response(self.get_serializer(connection).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="available-accounts")
    def available_accounts(self, request, public_id=None):
        connection = self.get_object()
        try:
            results = get_open_banking_adapter(connection.provider).list_accounts(connection=connection)
        except OpenBankingProviderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"results": results})

    @action(detail=True, methods=["post"], url_path="refresh-credentials")
    def refresh_credentials(self, request, public_id=None):
        try:
            connection = refresh_connection_credentials(self.get_object())
        except OpenBankingProviderError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(connection).data)

    @action(detail=True, methods=["post"], url_path="reconcile")
    def reconcile(self, request, public_id=None):
        connection = self.get_object()
        results = [
            reconcile_connection_account(account_link=link)
            for link in connection.account_links.filter(is_active=True).select_related("account", "connection")
        ]
        return Response({"results": results})

    @action(detail=True, methods=["get"], url_path="timeline")
    def timeline(self, request, public_id=None):
        events = self.get_object().timeline_events.order_by("occurred_at", "pk")[:500]
        return Response({"results": OpenBankingTimelineEventSerializer(events, many=True).data})


class OpenBankingWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, provider):
        descriptor = get_provider(provider)
        if descriptor is None:
            return Response({"detail": "Proveedor no soportado."}, status=status.HTTP_404_NOT_FOUND)
        raw_body = request.body
        signature = request.headers.get("Signature", "") or request.headers.get("X-Vexxo-Provider-Signature", "")
        timestamp_header = request.headers.get("X-Vexxo-Provider-Timestamp", "")
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        request_ip = (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")) or "unknown"
        rate = consume_rate_limit(
            scope=f"integrations:webhook:{descriptor.code}",
            subject=request_ip,
            limit=120,
            window_seconds=60,
        )
        if not rate.allowed:
            record_security_event(
                event_type="integrations.webhook.rate_limited",
                severity=SecurityAuditEvent.Severity.WARNING,
                request=request,
                source="integrations.open_banking",
                target_type="provider",
                target_id=descriptor.code,
            )
            return Response({"detail": "Limite temporal excedido."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        if not verify_webhook_signature(
            provider=descriptor.code,
            body=raw_body,
            signature=signature,
            timestamp=timestamp_header,
            callback_url=request.build_absolute_uri(),
            authorization=request.headers.get("Authorization", ""),
        ):
            record_security_event(
                event_type="integrations.webhook.signature_rejected",
                severity=SecurityAuditEvent.Severity.WARNING,
                request=request,
                source="integrations.open_banking",
                target_type="provider",
                target_id=descriptor.code,
                metadata={"timestamp_supplied": bool(timestamp_header)},
            )
            return Response({"detail": "Firma de webhook invalida."}, status=status.HTTP_403_FORBIDDEN)
        payload = _normalize_provider_webhook(descriptor.code, request.data, raw_body)
        serializer = OpenBankingWebhookSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        receipt, created = process_provider_webhook(
            provider=descriptor.code,
            payload=serializer.validated_data,
            raw_body=raw_body,
        )
        record_security_event(
            event_type="integrations.webhook.accepted",
            request=request,
            source="integrations.open_banking",
            target_type="webhook_receipt",
            target_id=str(receipt.pk),
            metadata={"provider": descriptor.code, "duplicate": not created},
        )
        return Response(
            {"accepted": True, "duplicate": not created, "receipt_id": receipt.pk, "status": receipt.status},
            status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK,
        )


def _normalize_provider_webhook(provider: str, payload: dict, raw_body: bytes) -> dict:
    data = dict(payload or {})
    if provider == "belvo":
        webhook_type = str(data.get("webhook_type") or data.get("type") or "")
        event_map = {
            "TRANSACTIONS": "transactions.available",
            "LINK": "connection.connected",
            "ERROR": "connection.error",
        }
        return {
            "event_id": str(data.get("webhook_id") or data.get("id") or hashlib.sha256(raw_body).hexdigest()),
            "event_type": event_map.get(webhook_type.upper(), webhook_type.lower().replace("_", ".")),
            "connection_id": str(data.get("link_id") or data.get("link") or ""),
            "vexxo_connection_id": data.get("external_id") or None,
            "status": str(data.get("status") or ""),
            "reason_code": str(data.get("code") or data.get("error_code") or ""),
            "occurred_at": data.get("created_at") or data.get("timestamp") or None,
            "sequence": data.get("sequence") or None,
        }
    if provider == "salt_edge":
        inner = data.get("data") if isinstance(data.get("data"), dict) else data
        stage = str(inner.get("stage") or inner.get("type") or "")
        event_type = "transactions.available" if "transaction" in stage.lower() else "connection.connected"
        if str(inner.get("status") or "").lower() in {"error", "failed"}:
            event_type = "connection.error"
        custom = inner.get("custom_fields") if isinstance(inner.get("custom_fields"), dict) else {}
        return {
            "event_id": str(inner.get("id") or data.get("id") or hashlib.sha256(raw_body).hexdigest()),
            "event_type": event_type,
            "connection_id": str(inner.get("connection_id") or inner.get("connection") or ""),
            "vexxo_connection_id": custom.get("vexxo_connection_id") or None,
            "status": str(inner.get("status") or ""),
            "reason_code": str(inner.get("error_class") or inner.get("error_message") or "")[:64],
            "occurred_at": inner.get("updated_at") or inner.get("created_at") or None,
            "sequence": inner.get("sequence") or None,
        }
    return data
