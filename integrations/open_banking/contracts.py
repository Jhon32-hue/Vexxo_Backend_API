from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date, parse_datetime


OPEN_BANKING_SCHEMA_VERSION = "open_banking.canonical.v1"
MAPPER_VERSIONS = {
    "local_mock": "local_mock.mapper.v1",
    "belvo": "belvo.mapper.v1",
    "salt_edge": "salt_edge.mapper.v1",
}


@dataclass(frozen=True)
class ProviderPage:
    items: list[dict]
    next_cursor: str = ""
    has_more: bool = False
    schema_version: str = OPEN_BANKING_SCHEMA_VERSION
    provider_request_id: str = ""


@dataclass(frozen=True)
class ReconciliationSnapshot:
    external_account_id: str
    currency: str
    current_balance: Decimal | None
    available_balance: Decimal | None
    as_of: datetime | None
    provider: str
    schema_version: str = OPEN_BANKING_SCHEMA_VERSION


def mapper_version(provider: str) -> str:
    return MAPPER_VERSIONS.get(provider, f"{provider}.mapper.v1")


def normalize_merchant_alias(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text).upper()
    return re.sub(r"\s+", " ", text).strip()[:180]


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("El proveedor reporto un monto invalido.") from exc


def _date(value: Any) -> str:
    raw = str(value or "").strip()
    parsed = parse_date(raw[:10])
    if parsed is None:
        parsed_datetime = parse_datetime(raw)
        parsed = parsed_datetime.date() if parsed_datetime else None
    if parsed is None:
        raise ValidationError("El proveedor reporto una fecha invalida.")
    return parsed.isoformat()


def _datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return parse_datetime(str(value))


def normalize_account(provider: str, row: dict, *, institution_name: str) -> dict:
    if provider == "belvo":
        balance = row.get("balance") if isinstance(row.get("balance"), dict) else {}
        return {
            "schema_version": OPEN_BANKING_SCHEMA_VERSION,
            "mapper_version": mapper_version(provider),
            "external_account_id": str(row.get("id") or ""),
            "name": str(row.get("name") or row.get("number") or institution_name)[:120],
            "mask": str(row.get("number") or "")[-4:],
            "type": str(row.get("type") or row.get("category") or "other").lower(),
            "currency": str(row.get("currency") or "COP").upper()[:3],
            "institution_name": institution_name,
            "current_balance": str(balance.get("current") or row.get("balance") or ""),
            "available_balance": str(balance.get("available") or ""),
            "provenance": "belvo.accounts",
        }
    if provider == "salt_edge":
        extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
        return {
            "schema_version": OPEN_BANKING_SCHEMA_VERSION,
            "mapper_version": mapper_version(provider),
            "external_account_id": str(row.get("id") or ""),
            "name": str(row.get("name") or institution_name)[:120],
            "mask": str(extra.get("account_number") or "")[-4:],
            "type": str(row.get("nature") or "other").lower(),
            "currency": str(row.get("currency_code") or "COP").upper()[:3],
            "institution_name": institution_name,
            "current_balance": str(row.get("balance") or ""),
            "available_balance": str(extra.get("available_amount") or ""),
            "provenance": "salt_edge.accounts",
        }
    result = dict(row)
    result.setdefault("schema_version", OPEN_BANKING_SCHEMA_VERSION)
    result.setdefault("mapper_version", mapper_version(provider))
    result.setdefault("provenance", f"{provider}.accounts")
    return result


def normalize_transaction(provider: str, row: dict) -> dict:
    if provider == "belvo":
        merchant = row.get("merchant") if isinstance(row.get("merchant"), dict) else {}
        raw_amount = _decimal(row.get("amount"))
        direction = str(row.get("type") or "").upper()
        is_credit = direction in {"INFLOW", "CREDIT"} or (not direction and raw_amount >= 0)
        provider_status = str(row.get("status") or "posted").lower()
        status = "pending" if provider_status in {"pending", "authorized"} else "posted"
        if provider_status in {"reversed", "cancelled", "canceled"}:
            status = "reversed"
        merchant_name = str(merchant.get("name") or "")[:180]
        return {
            "external_id": str(row.get("id") or ""),
            "provider_event_id": str(row.get("id") or ""),
            "provider_status": provider_status,
            "type": "income" if is_credit else "expense",
            "status": status,
            "amount": str(abs(raw_amount)),
            "date": _date(row.get("value_date") or row.get("accounting_date") or row.get("created_at")),
            "currency": str(row.get("currency") or "COP").upper()[:3],
            "description": str(row.get("description") or merchant_name or "Movimiento bancario")[:255],
            "merchant_name": merchant_name,
            "merchant_alias": normalize_merchant_alias(merchant_name),
            "merchant_category_code": str(merchant.get("mcc") or "")[:16],
            "credit_debit_indicator": "credit" if is_credit else "debit",
            "rail": "open_banking",
            "channel": "api",
            "data_origin": "open_banking",
            "confidence_score": 100,
            "classifier_name": "provider_category_passthrough",
            "classifier_version": mapper_version(provider),
            "feature_schema_version": OPEN_BANKING_SCHEMA_VERSION,
            "classification_source": "provider",
            "confirmed": status != "pending",
            "affects_balance": status != "pending",
            "metadata": {
                "schema_version": OPEN_BANKING_SCHEMA_VERSION,
                "mapper_version": mapper_version(provider),
                "provenance": "belvo.transactions",
            },
        }
    if provider == "salt_edge":
        extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
        raw_amount = _decimal(row.get("amount"))
        provider_status = str(row.get("status") or "posted").lower()
        status = "pending" if provider_status == "pending" else "posted"
        if provider_status in {"reversed", "cancelled", "canceled"}:
            status = "reversed"
        merchant_name = str(extra.get("merchant") or "")[:180]
        return {
            "external_id": str(row.get("id") or ""),
            "provider_event_id": str(row.get("id") or ""),
            "provider_status": provider_status,
            "type": "expense" if raw_amount < 0 else "income",
            "status": status,
            "amount": str(abs(raw_amount)),
            "date": _date(row.get("made_on") or row.get("created_at")),
            "currency": str(row.get("currency_code") or "COP").upper()[:3],
            "description": str(row.get("description") or merchant_name or "Movimiento bancario")[:255],
            "merchant_name": merchant_name,
            "merchant_alias": normalize_merchant_alias(merchant_name),
            "counterparty_name": str(extra.get("payee") or extra.get("payer") or "")[:180],
            "credit_debit_indicator": "debit" if raw_amount < 0 else "credit",
            "rail": "open_banking",
            "channel": "api",
            "data_origin": "open_banking",
            "confidence_score": 100,
            "classifier_name": "provider_category_passthrough",
            "classifier_version": mapper_version(provider),
            "feature_schema_version": OPEN_BANKING_SCHEMA_VERSION,
            "classification_source": "provider",
            "confirmed": status != "pending",
            "affects_balance": status != "pending",
            "metadata": {
                "schema_version": OPEN_BANKING_SCHEMA_VERSION,
                "mapper_version": mapper_version(provider),
                "provenance": "salt_edge.transactions",
                "provider_category": str(row.get("category") or "")[:64],
            },
        }
    normalized = dict(row)
    metadata = dict(normalized.get("metadata") or {})
    metadata.update(
        schema_version=OPEN_BANKING_SCHEMA_VERSION,
        mapper_version=mapper_version(provider),
        provenance=f"{provider}.transactions",
    )
    normalized["metadata"] = metadata
    if normalized.get("merchant_name"):
        normalized["merchant_alias"] = normalize_merchant_alias(normalized["merchant_name"])
    return normalized


def reconciliation_snapshot(provider: str, account: dict) -> ReconciliationSnapshot:
    current = account.get("current_balance")
    available = account.get("available_balance")
    return ReconciliationSnapshot(
        external_account_id=str(account.get("external_account_id") or ""),
        currency=str(account.get("currency") or "COP").upper()[:3],
        current_balance=_decimal(current) if current not in (None, "") else None,
        available_balance=_decimal(available) if available not in (None, "") else None,
        as_of=_datetime(account.get("balance_as_of")),
        provider=provider,
    )
