"""
Contratos declarativos de proveedores para `payments.payment_intents`.

Objetivo:
- definir de forma estable como Vexxo habla con cada PSP o rail
- separar contrato canonico del dominio vs payload concreto del proveedor
- permitir agregar proveedores nuevos cambiando mapping/configuracion y no
  redisenando `services`, `callback_service` o `finance.transactions`

Notas:
- esto no reemplaza adapters concretos; les da un contrato comun
- el callback contract define paths, estados y autenticacion esperada
- el dispatch contract define el envelope canonico que Vexxo entrega a
  integradores, workers o Cloud Run services
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _resolve_path(payload: dict[str, Any], path: str):
    current: Any = payload
    for part in str(path or "").split("."):
        if current in (None, ""):
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _normalize_decimal(value, transform: str = "decimal"):
    if value in (None, ""):
        return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if transform == "cents_to_decimal":
        decimal_value = decimal_value / Decimal("100")
    return decimal_value


def _normalize_string(value, *, uppercase: bool = False, lowercase: bool = False):
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if uppercase:
        return text.upper()
    if lowercase:
        return text.lower()
    return text


def _extract_value(payload: dict[str, Any], specs, default=None):
    for spec in specs or []:
        transform = None
        path = spec
        if isinstance(spec, dict):
            path = spec.get("path")
            transform = spec.get("transform")
        value = _resolve_path(payload, str(path or ""))
        if value in (None, ""):
            continue
        if transform == "cents_to_decimal":
            normalized = _normalize_decimal(value, transform="cents_to_decimal")
        elif transform == "decimal":
            normalized = _normalize_decimal(value, transform="decimal")
        elif transform == "uppercase":
            normalized = _normalize_string(value, uppercase=True)
        elif transform == "lowercase":
            normalized = _normalize_string(value, lowercase=True)
        else:
            normalized = value
        if normalized not in (None, ""):
            return normalized
    return default


DEFAULT_PROVIDER_CONTRACT = {
    "schema_version": "2026-04-02",
    "provider": "generic",
    "dispatch_contract": {
        "schema_name": "vexxo.payment.dispatch.v1",
        "required_fields": [
            "provider",
            "rail",
            "payment_intent_id",
            "internal_reference",
            "amount",
            "currency",
        ],
        "notes": [
            "Este envelope es canonico de Vexxo y se puede transformar despues al payload exacto del proveedor.",
            "El adapter puede agregar provider_payload o provider_headers sin romper la forma canonica.",
        ],
    },
    "callback_contract": {
        "schema_name": "vexxo.payment.provider_callback.v1",
        "identifiers_any_of": [
            "payment_intent_id",
            "provider_intent_id",
            "external_reference",
            "provider_reference",
        ],
        "meaningful_state_any_of": [
            "status",
            "issue_kind",
            "settlement_reference",
        ],
        "field_paths": {
            "provider_event_type": ["event", "event_type", "callback_type"],
            "callback_type": ["callback_type", "event_type", "event"],
            "status": [{"path": "status", "transform": "lowercase"}],
            "payment_intent_id": ["payment_intent_id"],
            "provider_intent_id": ["provider_intent_id"],
            "external_reference": ["external_reference", "reference"],
            "provider_reference": ["provider_reference"],
            "provider_cus": ["provider_cus"],
            "settlement_reference": ["settlement_reference"],
            "amount": [{"path": "amount", "transform": "decimal"}],
            "currency": [{"path": "currency", "transform": "uppercase"}],
            "issue_kind": [{"path": "issue_kind", "transform": "lowercase"}],
            "issue_reference": ["issue_reference"],
            "failure_code": ["failure_code"],
            "failure_message": ["failure_message", "message"],
            "metadata": ["metadata"],
        },
        "defaults": {
            "callback_type": "status",
            "currency": "COP",
        },
        "status_map": {
            "created": "created",
            "dispatched": "dispatched",
            "processing": "processing",
            "requires_action": "requires_action",
            "succeeded": "succeeded",
            "success": "succeeded",
            "failed": "failed",
            "cancelled": "cancelled",
            "canceled": "cancelled",
            "settled": "settled",
            "reversed": "reversed",
            "disputed": "disputed",
        },
        "issue_kind_map": {
            "refund": "refund",
            "reversal": "reversal",
            "reverse": "reversal",
            "chargeback": "dispute",
            "dispute": "dispute",
        },
        "signature": {
            "strategy": "hmac_sha256_body",
            "header": "X-Vexxo-Provider-Signature",
            "secret_setting_key": "callback_secret",
            "allow_unsigned_when_secret_missing": False,
        },
    },
}


PAYMENT_PROVIDER_CONTRACTS = {
    "generic": DEFAULT_PROVIDER_CONTRACT,
    "local_fake": _deep_merge(
        DEFAULT_PROVIDER_CONTRACT,
        {
            "provider": "local_fake",
            "schema_version": "2026-09-19",
        },
    ),
    "local-stub": _deep_merge(
        DEFAULT_PROVIDER_CONTRACT,
        {
            "provider": "local-stub",
            "schema_version": "2026-09-19",
        },
    ),
    "wompi": _deep_merge(
        DEFAULT_PROVIDER_CONTRACT,
        {
            "provider": "wompi",
            "callback_contract": {
                "field_paths": {
                    "provider_event_type": ["event", "data.event", "callback_type"],
                    "callback_type": ["event", "callback_type"],
                    "status": [
                        {"path": "data.transaction.status", "transform": "lowercase"},
                        {"path": "status", "transform": "lowercase"},
                    ],
                    "provider_intent_id": ["data.transaction.id", "provider_intent_id"],
                    "external_reference": [
                        "data.transaction.reference",
                        "data.reference",
                        "external_reference",
                    ],
                    "provider_reference": [
                        "data.transaction.id",
                        "provider_reference",
                    ],
                    "provider_cus": [
                        "data.transaction.payment_method.extra.cus",
                        "data.transaction.payment_method.extra.reference",
                        "provider_cus",
                    ],
                    "settlement_reference": [
                        "data.settlement.reference",
                        "settlement_reference",
                    ],
                    "amount": [
                        {"path": "data.transaction.amount_in_cents", "transform": "cents_to_decimal"},
                        {"path": "amount", "transform": "decimal"},
                    ],
                    "currency": [
                        {"path": "data.transaction.currency", "transform": "uppercase"},
                        {"path": "currency", "transform": "uppercase"},
                    ],
                    "issue_kind": [
                        {"path": "data.issue.kind", "transform": "lowercase"},
                        {"path": "issue_kind", "transform": "lowercase"},
                    ],
                    "issue_reference": ["data.issue.reference", "issue_reference"],
                    "failure_code": ["data.error.code", "failure_code"],
                    "failure_message": ["data.error.message", "failure_message", "message"],
                    "metadata": ["data", "metadata"],
                },
                "status_map": {
                    "approved": "succeeded",
                    "pending": "processing",
                    "voided": "cancelled",
                    "declined": "failed",
                    "error": "failed",
                    "processing": "processing",
                    "requires_action": "requires_action",
                    "settled": "settled",
                    "reversed": "reversed",
                    "disputed": "disputed",
                },
                "signature": {
                    "strategy": "wompi_event_checksum",
                    "header": "X-Event-Checksum",
                },
            },
        },
    ),
}


def get_payment_provider_contract(provider: str) -> dict[str, Any]:
    provider_code = str(provider or "").strip().lower() or "generic"
    contract = PAYMENT_PROVIDER_CONTRACTS.get(provider_code, PAYMENT_PROVIDER_CONTRACTS["generic"])
    return _deep_merge(contract, {"provider": provider_code})


def build_public_provider_contract(provider: str) -> dict[str, Any]:
    contract = get_payment_provider_contract(provider)
    callback_contract = dict(contract.get("callback_contract") or {})
    signature = dict(callback_contract.get("signature") or {})
    callback_contract["signature"] = {
        "strategy": signature.get("strategy"),
        "header": signature.get("header"),
        "allow_unsigned_when_secret_missing": signature.get("allow_unsigned_when_secret_missing", False),
    }
    return {
        "provider": contract.get("provider"),
        "schema_version": contract.get("schema_version"),
        "dispatch_contract": contract.get("dispatch_contract") or {},
        "callback_contract": callback_contract,
    }


def extract_contract_callback_fields(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    contract = get_payment_provider_contract(provider)
    callback_contract = dict(contract.get("callback_contract") or {})
    field_paths = dict(callback_contract.get("field_paths") or {})
    defaults = dict(callback_contract.get("defaults") or {})
    normalized = {
        "provider": contract.get("provider"),
        "contract_version": contract.get("schema_version"),
        "provider_event_type": _extract_value(payload, field_paths.get("provider_event_type"), default=""),
        "callback_type": _extract_value(payload, field_paths.get("callback_type"), default=defaults.get("callback_type", "status")),
        "status": _extract_value(payload, field_paths.get("status"), default=""),
        "payment_intent_id": _extract_value(payload, field_paths.get("payment_intent_id"), default=""),
        "provider_intent_id": _extract_value(payload, field_paths.get("provider_intent_id"), default=""),
        "external_reference": _extract_value(payload, field_paths.get("external_reference"), default=""),
        "provider_reference": _extract_value(payload, field_paths.get("provider_reference"), default=""),
        "provider_cus": _extract_value(payload, field_paths.get("provider_cus"), default=""),
        "settlement_reference": _extract_value(payload, field_paths.get("settlement_reference"), default=""),
        "amount": _extract_value(payload, field_paths.get("amount"), default=None),
        "currency": _extract_value(payload, field_paths.get("currency"), default=defaults.get("currency", "COP")),
        "issue_kind": _extract_value(payload, field_paths.get("issue_kind"), default=""),
        "issue_reference": _extract_value(payload, field_paths.get("issue_reference"), default=""),
        "failure_code": _extract_value(payload, field_paths.get("failure_code"), default=""),
        "failure_message": _extract_value(payload, field_paths.get("failure_message"), default=""),
        "metadata": _extract_value(payload, field_paths.get("metadata"), default={}) or {},
        "raw": payload or {},
    }
    status_map = {str(k).strip().lower(): v for k, v in dict(callback_contract.get("status_map") or {}).items()}
    issue_map = {str(k).strip().lower(): v for k, v in dict(callback_contract.get("issue_kind_map") or {}).items()}
    normalized["status"] = status_map.get(str(normalized["status"]).strip().lower(), str(normalized["status"]).strip().lower())
    normalized["issue_kind"] = issue_map.get(
        str(normalized["issue_kind"]).strip().lower(),
        str(normalized["issue_kind"]).strip().lower(),
    )
    normalized["callback_type"] = _normalize_string(normalized["callback_type"])
    normalized["provider_event_type"] = _normalize_string(normalized["provider_event_type"])
    normalized["payment_intent_id"] = _normalize_string(normalized["payment_intent_id"])
    normalized["provider_intent_id"] = _normalize_string(normalized["provider_intent_id"])
    normalized["external_reference"] = _normalize_string(normalized["external_reference"])
    normalized["provider_reference"] = _normalize_string(normalized["provider_reference"])
    normalized["provider_cus"] = _normalize_string(normalized["provider_cus"])
    normalized["settlement_reference"] = _normalize_string(normalized["settlement_reference"])
    normalized["currency"] = _normalize_string(normalized["currency"], uppercase=True) or "COP"
    normalized["issue_reference"] = _normalize_string(normalized["issue_reference"])
    normalized["failure_code"] = _normalize_string(normalized["failure_code"])
    normalized["failure_message"] = _normalize_string(normalized["failure_message"])
    return normalized

