from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from finance.accounts.models import Account
from integrations.open_banking.models import OpenBankingAccountLink


LOCAL_MOCK_FIXTURE_VERSION = "2026-09-v1"


def list_local_mock_accounts(*, connection) -> list[dict]:
    if connection.provider != "local_mock":
        return []
    prefix = f"lm-{connection.public_id.hex[:12]}"
    return [
        {
            "external_account_id": f"{prefix}-checking",
            "name": "Cuenta corriente local mock",
            "mask": "1042",
            "type": "checking",
            "currency": "COP",
            "institution_name": connection.institution_name,
            "fixture_version": LOCAL_MOCK_FIXTURE_VERSION,
        },
        {
            "external_account_id": f"{prefix}-savings",
            "name": "Cuenta de ahorros local mock",
            "mask": "7781",
            "type": "savings",
            "currency": "COP",
            "institution_name": connection.institution_name,
            "fixture_version": LOCAL_MOCK_FIXTURE_VERSION,
        },
    ]


def get_local_mock_account(*, connection, external_account_id: str) -> dict | None:
    requested_id = str(external_account_id or "").strip()
    return next(
        (
            account
            for account in list_local_mock_accounts(connection=connection)
            if account["external_account_id"] == requested_id
        ),
        None,
    )


def _stable_amount(external_account_id: str, *, base: str, spread: int) -> str:
    digest = hashlib.sha256(external_account_id.encode("utf-8")).hexdigest()
    offset = int(digest[:8], 16) % max(1, spread)
    return str((Decimal(base) + Decimal(offset * 100)).quantize(Decimal("0.01")))


def build_local_mock_snapshot(*, account: Account) -> dict:
    link = (
        OpenBankingAccountLink.objects.select_related("connection")
        .filter(account=account, is_active=True, connection__provider="local_mock")
        .first()
    )
    if link is None:
        raise ValueError("La cuenta no tiene un enlace local_mock activo.")

    anchor_date = timezone.localdate(link.created_at)
    external_account_id = link.external_account_id
    prefix = f"{external_account_id}:{LOCAL_MOCK_FIXTURE_VERSION}"
    currency = account.currency or "COP"
    rows = [
        {
            "external_id": f"{prefix}:salary",
            "provider_event_id": f"{prefix}:salary",
            "provider_status": "posted",
            "type": "income",
            "status": "posted",
            "amount": _stable_amount(external_account_id, base="3200000", spread=1200),
            "date": str(anchor_date - timedelta(days=4)),
            "currency": currency,
            "description": "Nomina empresa demo",
            "counterparty_name": "Empresa Demo SAS",
            "credit_debit_indicator": "credit",
            "rail": "open_banking",
            "channel": "api",
            "settlement_status": "settled",
            "country_code": account.country or "CO",
            "data_origin": "open_banking",
            "confidence_score": 100,
            "confirmed": True,
            "affects_balance": True,
            "metadata": {"fixture_version": LOCAL_MOCK_FIXTURE_VERSION, "scenario": "salary"},
        },
        {
            "external_id": f"{prefix}:groceries",
            "provider_event_id": f"{prefix}:groceries",
            "provider_status": "posted",
            "type": "expense",
            "status": "posted",
            "amount": _stable_amount(external_account_id, base="164900", spread=350),
            "date": str(anchor_date - timedelta(days=3)),
            "currency": currency,
            "description": "Compra supermercado local",
            "merchant_name": "Mercado Vexxo Demo",
            "merchant_category_code": "5411",
            "credit_debit_indicator": "debit",
            "rail": "open_banking",
            "channel": "card_present",
            "authorization_status": "authorized",
            "settlement_status": "settled",
            "country_code": account.country or "CO",
            "data_origin": "open_banking",
            "confidence_score": 100,
            "confirmed": True,
            "affects_balance": True,
            "metadata": {"fixture_version": LOCAL_MOCK_FIXTURE_VERSION, "scenario": "groceries"},
        },
        {
            "external_id": f"{prefix}:utilities",
            "provider_event_id": f"{prefix}:utilities",
            "provider_status": "posted",
            "type": "expense",
            "status": "posted",
            "amount": _stable_amount(external_account_id, base="118500", spread=220),
            "date": str(anchor_date - timedelta(days=2)),
            "currency": currency,
            "description": "Pago servicio de energia",
            "counterparty_name": "Servicios Publicos Demo",
            "credit_debit_indicator": "debit",
            "rail": "open_banking",
            "channel": "bank_transfer",
            "settlement_status": "settled",
            "country_code": account.country or "CO",
            "data_origin": "open_banking",
            "confidence_score": 100,
            "confirmed": True,
            "affects_balance": True,
            "metadata": {"fixture_version": LOCAL_MOCK_FIXTURE_VERSION, "scenario": "utilities"},
        },
        {
            "external_id": f"{prefix}:coffee",
            "provider_event_id": f"{prefix}:coffee",
            "provider_status": "posted",
            "type": "expense",
            "status": "posted",
            "amount": _stable_amount(external_account_id, base="12900", spread=35),
            "date": str(anchor_date - timedelta(days=1)),
            "currency": currency,
            "description": "Cafe de prueba",
            "merchant_name": "Cafe Local Demo",
            "merchant_category_code": "5814",
            "credit_debit_indicator": "debit",
            "rail": "open_banking",
            "channel": "card_present",
            "authorization_status": "authorized",
            "settlement_status": "settled",
            "country_code": account.country or "CO",
            "data_origin": "open_banking",
            "confidence_score": 100,
            "confirmed": True,
            "affects_balance": True,
            "metadata": {"fixture_version": LOCAL_MOCK_FIXTURE_VERSION, "scenario": "coffee"},
        },
    ]
    return {
        "provider": "local_mock",
        "source": "open_banking",
        "provider_account_id": external_account_id,
        "cursor": f"local-mock:{LOCAL_MOCK_FIXTURE_VERSION}",
        "fixture_version": LOCAL_MOCK_FIXTURE_VERSION,
        "connection_id": str(link.connection.public_id),
        "rows": rows,
    }


def record_local_mock_sync(*, account: Account, cursor: str, intake_result: dict, next_sync_at) -> None:
    link = (
        OpenBankingAccountLink.objects.select_for_update()
        .select_related("connection")
        .filter(account=account, is_active=True, connection__provider="local_mock")
        .first()
    )
    if link is None:
        return

    now = timezone.now()
    link.sync_cursor = cursor
    link.save(update_fields=["sync_cursor", "updated_at"])

    connection = link.connection
    connection.status = connection.Status.CONNECTED
    connection.last_synced_at = now
    connection.next_sync_at = next_sync_at
    connection.error_code = ""
    connection.error_message = ""
    connection.safe_metadata = {
        **(connection.safe_metadata or {}),
        "fixture_version": LOCAL_MOCK_FIXTURE_VERSION,
        "last_intake_batch_id": intake_result.get("batch_id", ""),
        "last_intake_counts": intake_result.get("counts", {}),
        "last_sync_row_count": intake_result.get("total", 0),
    }
    connection.save(
        update_fields=[
            "status",
            "last_synced_at",
            "next_sync_at",
            "error_code",
            "error_message",
            "safe_metadata",
            "updated_at",
        ]
    )
