from __future__ import annotations

import hashlib
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from integrations.credentials.models import IntegrationCredential
from integrations.credentials.services import revoke_credential
from rest_framework.exceptions import ValidationError

from alerts.alerts.models.alerts import AlertCategory, AlertSeverity, AlertType
from alerts.alerts.services import create_alert
from finance.accounts.models import (
    Account,
    AccountDataOrigin,
    AccountRole,
    AccountSensitivityLevel,
    AccountSourcePriority,
    AccountType,
    AccountVerificationLevel,
)
from finance.accounts.services.account_lifecycle_service import create_account
from finance.accounts.services.account_policy_service import validate_account_external_link_allowed
from finance.accounts.services.account_sync_service import (
    link_account_external_source,
    schedule_account_sync,
    unlink_account_external_source,
)
from identity.consents.models import ConsentType
from identity.consents.services import grant_consent, revoke_consent
from integrations.open_banking.models import (
    OpenBankingAccountLink,
    OpenBankingConnection,
    OpenBankingExternalPayload,
    OpenBankingInstitution,
    OpenBankingWebhookReceipt,
)
from integrations.open_banking.adapters import OpenBankingProviderError, get_open_banking_adapter
from integrations.open_banking.lifecycle import (
    mark_payload_failed,
    mark_payload_normalized,
    quarantine_external_payload,
    record_timeline,
)
from integrations.open_banking.provider_catalog import get_provider
from notifications.deliveries.services import create_notification_delivery


DEFAULT_SCOPES = ("accounts", "balances", "transactions")
LOCAL_MOCK_CONSENT_DAYS = 90

ACCOUNT_TYPE_MAP = {
    "checking": (AccountType.BANK, AccountRole.SPENDING),
    "current": (AccountType.BANK, AccountRole.SPENDING),
    "savings": (AccountType.SAVINGS, AccountRole.SPENDING),
    "credit": (AccountType.CREDIT, AccountRole.CREDIT_LINE),
    "credit_card": (AccountType.CREDIT, AccountRole.CREDIT_LINE),
    "loan": (AccountType.LOAN, AccountRole.CREDIT_LINE),
    "investment": (AccountType.INVESTMENT, AccountRole.INVEST_PORTFOLIO),
    "wallet": (AccountType.WALLET, AccountRole.SPENDING),
}


@transaction.atomic
def start_open_banking_connection(
    *,
    owner,
    provider_code: str,
    institution_name: str,
    country: str,
    scopes: list[str] | None,
    idempotency_key: str,
    institution: OpenBankingInstitution | None = None,
) -> OpenBankingConnection:
    provider = get_provider(provider_code)
    if provider is None:
        raise ValidationError({"provider": "Proveedor open banking no soportado."})
    if not provider.available:
        raise ValidationError({"provider": "El adapter del proveedor no esta disponible para conexiones."})
    normalized_key = (idempotency_key or "").strip()
    if not normalized_key:
        raise ValidationError({"idempotency_key": "Idempotency-Key es requerido."})
    existing = OpenBankingConnection.objects.filter(owner=owner, idempotency_key=normalized_key).first()
    if existing is not None:
        return existing

    normalized_scopes = sorted(
        set(scope for scope in (scopes or DEFAULT_SCOPES) if scope in provider.capabilities)
    )
    if not normalized_scopes:
        raise ValidationError({"scopes": "La conexion requiere al menos un scope soportado."})
    if institution is None and provider.local_only:
        institution = OpenBankingInstitution.objects.filter(code="vexxo-local-development", is_active=True).first()
    if institution is not None and country and institution.country != country.upper()[:2]:
        raise ValidationError({"institution_code": "La institucion no corresponde al pais solicitado."})
    canonical_institution_name = institution.name if institution else (institution_name or provider.name)
    canonical_country = institution.country if institution else (country or "").upper()[:2]
    consent = grant_consent(
        user=owner,
        data={
            "consent_type": ConsentType.OPEN_BANKING_DATA,
            "provider": provider.code,
            "external_consent_id": f"{provider.code}:{hashlib.sha256(normalized_key.encode()).hexdigest()[:32]}",
            "scope_code": " ".join(normalized_scopes),
            "purpose": "Sincronizar cuentas, saldos y movimientos autorizados por el usuario.",
            "legal_basis": "consent",
            "granted_via": "mobile_open_banking",
            "data_categories": normalized_scopes,
            "expires_at": timezone.now() + timedelta(days=LOCAL_MOCK_CONSENT_DAYS)
            if provider.local_only
            else None,
            "metadata": {
                "country": canonical_country,
                "revocable_at_any_time": True,
                "authorization_channel": "vexxo_mobile",
            },
        },
    )
    status = (
        OpenBankingConnection.Status.CONNECTED
        if provider.local_only
        else OpenBankingConnection.Status.PENDING_AUTHORIZATION
    )
    connection = OpenBankingConnection.objects.create(
        owner=owner,
        consent=consent,
        provider=provider.code,
        idempotency_key=normalized_key,
        institution_name=canonical_institution_name[:120],
        institution=institution,
        country=canonical_country,
        status=status,
        scopes=normalized_scopes,
        safe_metadata={"adapter_mode": "local_mock" if provider.local_only else "provider"},
    )
    if not provider.local_only:
        authorization = get_open_banking_adapter(provider.code).begin_authorization(connection=connection)
        connection.safe_metadata = {
            **connection.safe_metadata,
            "external_customer_id": authorization.external_customer_id,
        }
        connection.save(update_fields=["safe_metadata", "updated_at"])
        connection._authorization_url = authorization.authorization_url
        connection._widget_access_token = authorization.widget_access_token
    create_notification_delivery(
        owner=owner,
        title="Conexion bancaria iniciada",
        message=f"Vexxo preparo la conexion con {connection.institution_name}.",
        event_type="integrations.open_banking.connection_started.v1",
        source="integrations.open_banking",
        payload={"connection_id": str(connection.public_id), "provider": provider.code},
        dedupe_key=f"open-banking-started:{connection.pk}",
    )
    record_timeline(
        connection=connection,
        event_type="connection.started",
        source="integrations.open_banking.services",
        status=connection.status,
        metadata={"provider": provider.code, "institution_code": institution.code if institution else ""},
    )
    return connection


@transaction.atomic
def materialize_provider_account(
    *,
    connection: OpenBankingConnection,
    external_account_id: str,
) -> OpenBankingAccountLink:
    if connection.status != OpenBankingConnection.Status.CONNECTED:
        raise ValidationError({"connection": "Solo una conexion activa puede importar productos."})

    external_id = str(external_account_id or "").strip()
    existing = (
        OpenBankingAccountLink.objects.select_related("account")
        .filter(connection=connection, external_account_id=external_id)
        .first()
    )
    if existing is not None:
        return existing

    descriptor = next(
        (
            item
            for item in get_open_banking_adapter(connection.provider).list_accounts(connection=connection)
            if item["external_account_id"] == external_id
        ),
        None,
    )
    if descriptor is None:
        raise ValidationError({"external_account_id": "El proveedor no reporto ese producto bancario."})

    external_type = str(descriptor.get("type") or "").lower()
    account_type, account_role = ACCOUNT_TYPE_MAP.get(
        external_type,
        (AccountType.OTHER, AccountRole.OBSERVED_ONLY),
    )
    account = Account(
        owner=connection.owner,
        name=str(descriptor.get("name") or connection.institution_name)[:120],
        type=account_type,
        role=account_role,
        currency=str(descriptor.get("currency") or "COP")[:10],
        country=connection.country,
        institution=connection.institution_name,
        base_currency=getattr(connection.owner, "preferred_currency", "") or "COP",
        data_origin=AccountDataOrigin.SYNCED,
        verification_level=AccountVerificationLevel.EXTERNALLY_VERIFIED,
        source_priority=AccountSourcePriority.PROVIDER,
        sensitivity_level=AccountSensitivityLevel.SENSITIVE,
        confidence_score=100,
    )
    validate_account_external_link_allowed(account=account)
    account.save()
    create_account(account)
    link_account_external_source(
        account=account,
        data={
            "provider": connection.provider,
            "external_id": external_id,
            "external_mask": str(descriptor.get("mask") or "")[:16],
            "external_type": external_type[:64],
            "provider_metadata": {
                "open_banking_connection_id": str(connection.public_id),
                "institution_name": connection.institution_name,
                "country": connection.country,
                "adapter": connection.provider,
            },
        },
    )
    link = OpenBankingAccountLink.objects.create(
        connection=connection,
        account=account,
        external_account_id=external_id,
        external_mask=str(descriptor.get("mask") or "")[:16],
        external_type=external_type[:64],
    )
    record_timeline(
        connection=connection,
        event_type="account.linked",
        source="integrations.open_banking.services",
        status="active",
        metadata={"account_link_id": link.pk, "account_id": account.pk, "external_type": external_type[:64]},
    )
    return link


@transaction.atomic
def link_existing_account(
    *,
    connection: OpenBankingConnection,
    account: Account,
    external_account_id: str,
    external_mask: str = "",
    external_type: str = "",
) -> OpenBankingAccountLink:
    if connection.owner_id != account.owner_id:
        raise ValidationError({"account_id": "La cuenta debe pertenecer al propietario de la conexion."})
    if connection.status not in {
        OpenBankingConnection.Status.CONNECTED,
        OpenBankingConnection.Status.ATTENTION_REQUIRED,
    }:
        raise ValidationError({"connection": "La conexion no esta lista para enlazar cuentas."})
    validate_account_external_link_allowed(account=account)
    external_id = (external_account_id or "").strip()
    if not external_id:
        raise ValidationError({"external_account_id": "El identificador externo es requerido."})

    link_account_external_source(
        account=account,
        data={
            "provider": connection.provider,
            "external_id": external_id,
            "external_mask": (external_mask or "")[:16],
            "external_type": (external_type or "")[:64],
            "provider_metadata": {"open_banking_connection_id": str(connection.public_id)},
        },
    )
    link, _ = OpenBankingAccountLink.objects.update_or_create(
        connection=connection,
        external_account_id=external_id,
        defaults={
            "account": account,
            "external_mask": (external_mask or "")[:16],
            "external_type": (external_type or "")[:64],
            "is_active": True,
        },
    )
    return link


@transaction.atomic
def request_connection_sync(connection: OpenBankingConnection) -> OpenBankingConnection:
    if connection.status != OpenBankingConnection.Status.CONNECTED:
        raise ValidationError({"connection": "Solo una conexion activa puede sincronizarse."})
    if connection.provider != "local_mock":
        get_open_banking_adapter(connection.provider).request_sync(connection=connection)
        connection.status = OpenBankingConnection.Status.SYNCING
        connection.next_sync_at = timezone.now()
        connection.save(update_fields=["status", "next_sync_at", "updated_at"])
        record_timeline(
            connection=connection,
            event_type="sync.requested",
            source="integrations.open_banking.services",
            status=connection.status,
        )
        return connection
    schedule_connection_account_imports(connection)
    connection.next_sync_at = timezone.now()
    connection.safe_metadata = {
        **(connection.safe_metadata or {}),
        "last_sync_requested_at": timezone.now().isoformat(),
    }
    connection.save(update_fields=["next_sync_at", "safe_metadata", "updated_at"])
    record_timeline(
        connection=connection,
        event_type="sync.requested",
        source="integrations.open_banking.services",
        status=connection.status,
    )
    return connection


def schedule_connection_account_imports(connection: OpenBankingConnection) -> int:
    scheduled = 0
    for link in connection.account_links.filter(is_active=True).select_related("account"):
        sync_window = timezone.now().strftime("%Y%m%d%H%M")
        schedule_account_sync(
            account=link.account,
            data={
                "run_at": timezone.now(),
                "sync_run_id": f"ob-{connection.pk}-{link.pk}-{sync_window}",
            },
        )
        scheduled += 1
    return scheduled


@transaction.atomic
def revoke_open_banking_connection(connection: OpenBankingConnection, *, reason: str = "user_requested"):
    connection = OpenBankingConnection.objects.select_for_update().select_related("consent").get(pk=connection.pk)
    if connection.status == OpenBankingConnection.Status.REVOKED:
        return connection
    provider_revocation = "confirmed"
    try:
        get_open_banking_adapter(connection.provider).revoke(connection=connection)
    except OpenBankingProviderError as exc:
        provider_revocation = "retry_required"
        connection.error_code = exc.code[:64]
        connection.error_message = "La revocacion local se aplico; falta confirmar el proveedor."
    _teardown_connection_access(
        connection=connection,
        reason=reason,
        provider_revocation=provider_revocation,
    )
    revoke_consent(connection.consent, reason=reason)
    create_notification_delivery(
        owner=connection.owner,
        title="Conexion bancaria revocada",
        message=f"Vexxo dejo de sincronizar {connection.institution_name}.",
        event_type="integrations.open_banking.connection_revoked.v1",
        source="integrations.open_banking",
        payload={"connection_id": str(connection.public_id)},
        dedupe_key=f"open-banking-revoked:{connection.pk}",
    )
    record_timeline(
        connection=connection,
        event_type="connection.revoked",
        source="integrations.open_banking.services",
        status=connection.status,
        metadata={"reason": reason, "provider_revocation": provider_revocation},
    )
    return connection


def _teardown_connection_access(
    *, connection: OpenBankingConnection, reason: str, provider_revocation: str = "not_requested"
) -> int:
    disabled_links = 0
    for link in connection.account_links.select_for_update().filter(is_active=True).select_related("account"):
        if (
            link.account.provider == connection.provider
            and link.account.external_id == link.external_account_id
        ):
            unlink_account_external_source(link.account)
        link.is_active = False
        link.save(update_fields=["is_active", "updated_at"])
        disabled_links += 1

    for credential in IntegrationCredential.objects.select_for_update().filter(
        owner=connection.owner,
        provider=connection.provider,
        external_reference=str(connection.public_id),
        status=IntegrationCredential.Status.ACTIVE,
    ):
        revoke_credential(credential)

    now = timezone.now()
    connection.status = OpenBankingConnection.Status.REVOKED
    connection.revoked_at = now
    connection.next_sync_at = None
    connection.safe_metadata = {
        **(connection.safe_metadata or {}),
        "revocation": {
            "reason": reason,
            "revoked_at": now.isoformat(),
            "future_collection_stopped": True,
            "provider_revocation": provider_revocation,
            "retained_data": "canonical_ledger_and_audit_subject_to_retention_policy",
        },
    }
    connection.save(
        update_fields=[
            "status", "revoked_at", "next_sync_at", "safe_metadata",
            "error_code", "error_message", "updated_at",
        ]
    )
    return disabled_links


@transaction.atomic
def teardown_open_banking_connections_for_consent_revocation(
    *,
    user,
    provider: str = "",
    reason: str = "consent_revoked",
) -> dict:
    connections = OpenBankingConnection.objects.select_for_update().filter(owner=user).exclude(
        status=OpenBankingConnection.Status.REVOKED
    )
    if provider:
        connections = connections.filter(provider__iexact=provider)

    revoked_connections = 0
    disabled_links = 0
    for connection in connections:
        provider_revocation = "confirmed"
        try:
            get_open_banking_adapter(connection.provider).revoke(connection=connection)
        except OpenBankingProviderError:
            provider_revocation = "retry_required"
        disabled_links += _teardown_connection_access(
            connection=connection,
            reason=reason,
            provider_revocation=provider_revocation,
        )
        revoked_connections += 1
    return {
        "revoked_connections": revoked_connections,
        "disabled_links": disabled_links,
    }


@transaction.atomic
def process_provider_webhook(*, provider: str, payload: dict, raw_body: bytes) -> tuple[OpenBankingWebhookReceipt, bool]:
    event_id = str(payload.get("event_id") or payload.get("id") or "").strip()
    event_type = str(payload.get("event_type") or payload.get("type") or "").strip()
    connection_reference = str(payload.get("connection_id") or payload.get("link_id") or "").strip()
    provider_occurred_at = payload.get("occurred_at")
    provider_sequence = payload.get("sequence")
    if not event_id or not event_type:
        raise ValidationError("event_id y event_type son requeridos.")
    receipt, created = OpenBankingWebhookReceipt.objects.get_or_create(
        provider=provider,
        provider_event_id=event_id,
        defaults={
            "event_type": event_type[:96],
            "payload_sha256": hashlib.sha256(raw_body).hexdigest(),
            "signature_verified": True,
            "connection_reference": connection_reference[:160],
            "provider_occurred_at": provider_occurred_at,
            "provider_sequence": provider_sequence,
            "safe_metadata": {
                "provider_status": str(payload.get("status") or "")[:64],
                "reason_code": str(payload.get("reason_code") or "")[:64],
            },
        },
    )
    if not created:
        return receipt, False

    connection = OpenBankingConnection.objects.filter(
        provider=provider,
        external_connection_id=connection_reference,
    ).first()
    if connection is None and payload.get("vexxo_connection_id"):
        connection = OpenBankingConnection.objects.filter(
            provider=provider,
            public_id=payload["vexxo_connection_id"],
        ).first()
        if connection is not None and connection_reference:
            connection.external_connection_id = connection_reference[:160]
            connection.save(update_fields=["external_connection_id", "updated_at"])
    if connection is None:
        receipt.status = OpenBankingWebhookReceipt.Status.REJECTED
        receipt.error_code = "connection_not_found"
    elif (
        connection.status == OpenBankingConnection.Status.REVOKED
        and event_type != "connection.revoked"
    ):
        receipt.status = OpenBankingWebhookReceipt.Status.REJECTED
        receipt.error_code = "connection_revoked"
    elif _is_out_of_order_callback(
        connection=connection,
        provider_occurred_at=provider_occurred_at,
        provider_sequence=provider_sequence,
    ):
        receipt.status = OpenBankingWebhookReceipt.Status.REJECTED
        receipt.error_code = "out_of_order"
    else:
        quarantine, _ = quarantine_external_payload(
            connection=connection,
            resource_type=OpenBankingExternalPayload.ResourceType.WEBHOOK,
            payload=payload,
            schema_version="open_banking.webhook.v1",
            provenance=f"{provider}.webhook",
        )
        try:
            _apply_connection_webhook(connection=connection, event_type=event_type, payload=payload)
            _advance_provider_event_clock(
                connection=connection,
                provider_occurred_at=provider_occurred_at,
                provider_sequence=provider_sequence,
            )
            mark_payload_normalized(quarantine)
            receipt.status = OpenBankingWebhookReceipt.Status.PROCESSED
        except Exception as exc:
            mark_payload_failed(quarantine, exc)
            receipt.status = OpenBankingWebhookReceipt.Status.FAILED
            receipt.error_code = "processing_failed"
    receipt.processed_at = timezone.now()
    receipt.save(update_fields=["status", "error_code", "processed_at"])
    if connection is not None:
        record_timeline(
            connection=connection,
            event_type=f"webhook.{event_type}",
            source="integrations.open_banking.webhook",
            status=receipt.status,
            provider_event_id=event_id,
            occurred_at=provider_occurred_at,
            metadata={"receipt_id": receipt.pk, "error_code": receipt.error_code},
        )
    return receipt, True


def _is_out_of_order_callback(*, connection, provider_occurred_at, provider_sequence) -> bool:
    if provider_sequence is not None and connection.last_provider_sequence is not None:
        if int(provider_sequence) < int(connection.last_provider_sequence):
            return True
    return bool(
        provider_occurred_at
        and connection.last_provider_event_at
        and provider_occurred_at < connection.last_provider_event_at
    )


def _advance_provider_event_clock(*, connection, provider_occurred_at, provider_sequence) -> None:
    update_fields = []
    if provider_occurred_at and (
        connection.last_provider_event_at is None or provider_occurred_at >= connection.last_provider_event_at
    ):
        connection.last_provider_event_at = provider_occurred_at
        update_fields.append("last_provider_event_at")
    if provider_sequence is not None and (
        connection.last_provider_sequence is None or int(provider_sequence) >= connection.last_provider_sequence
    ):
        connection.last_provider_sequence = int(provider_sequence)
        update_fields.append("last_provider_sequence")
    if update_fields:
        connection.save(update_fields=[*update_fields, "updated_at"])


def _apply_connection_webhook(*, connection: OpenBankingConnection, event_type: str, payload: dict) -> None:
    if connection.status == OpenBankingConnection.Status.REVOKED:
        return
    if event_type == "connection.connected":
        connection.status = OpenBankingConnection.Status.CONNECTED
        connection.error_code = ""
        connection.error_message = ""
        connection.save(update_fields=["status", "error_code", "error_message", "updated_at"])
        return
    if event_type == "transactions.available":
        if connection.status != OpenBankingConnection.Status.REVOKED:
            connection.status = OpenBankingConnection.Status.CONNECTED
            connection.save(update_fields=["status", "updated_at"])
            schedule_connection_account_imports(connection)
        return
    if event_type in {"connection.error", "connection.expired"}:
        connection.status = OpenBankingConnection.Status.ATTENTION_REQUIRED
        connection.error_code = str(payload.get("reason_code") or event_type)[:64]
        connection.error_message = "La conexion bancaria requiere atencion del usuario."
        connection.save(update_fields=["status", "error_code", "error_message", "updated_at"])
        create_alert(
            owner=connection.owner,
            type=AlertType.SYSTEM,
            category=AlertCategory.SYSTEM,
            severity=AlertSeverity.WARNING,
            title="Revisa tu conexion bancaria",
            message=f"La conexion con {connection.institution_name} necesita autorizacion.",
            source="integrations.open_banking.webhook",
            payload={"connection_id": str(connection.public_id), "reason_code": connection.error_code},
            correlation_id=f"open-banking:{connection.pk}",
        )
        return
    if event_type == "connection.revoked":
        revoke_open_banking_connection(connection, reason="provider_revoked")
