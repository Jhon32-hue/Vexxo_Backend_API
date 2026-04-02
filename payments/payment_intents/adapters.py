"""
Registry y contratos base para adapters de PSP/retailers.

La idea es que el dominio no se acople a Wompi ni a un proveedor concreto.
Cuando llegue un rail real, se implementa un adapter nuevo sin mover el resto
del bounded context.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any

from django.conf import settings

from payments.payment_intents.provider_contracts import (
    build_public_provider_contract,
    extract_contract_callback_fields,
    get_payment_provider_contract,
)


def _provider_settings() -> dict:
    return dict(getattr(settings, "PAYMENTS_PROVIDER_SETTINGS", {}) or {})


class PaymentProviderContractError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_provider_contract"):
        super().__init__(message)
        self.code = code


def _get_header_value(headers: dict | None, header_name: str) -> str:
    target = str(header_name or "").strip().lower()
    for key, value in (headers or {}).items():
        if str(key or "").strip().lower() == target:
            return str(value or "").strip()
    return ""


class BasePaymentProviderAdapter:
    provider_code = "generic"

    def provider_settings(self) -> dict[str, Any]:
        return dict(_provider_settings().get(self.provider_code, {}) or {})

    def provider_contract(self) -> dict[str, Any]:
        return get_payment_provider_contract(self.provider_code)

    def describe_contract(self) -> dict[str, Any]:
        return build_public_provider_contract(self.provider_code)

    def build_dispatch_payload(self, payment_intent) -> dict[str, Any]:
        contract = self.provider_contract()
        return {
            "schema": str(contract.get("dispatch_contract", {}).get("schema_name") or "vexxo.payment.dispatch.v1"),
            "provider": payment_intent.provider,
            "provider_contract_version": contract.get("schema_version"),
            "payment_intent": {
                "payment_intent_id": str(payment_intent.pk),
                "internal_reference": payment_intent.internal_reference,
                "external_reference": payment_intent.external_reference,
                "invoice_reference": payment_intent.invoice_reference,
                "payment_type": payment_intent.payment_type,
                "rail": payment_intent.rail,
                "amount": str(payment_intent.amount),
                "currency": payment_intent.currency,
                "source": payment_intent.source,
            },
            "beneficiary": {
                "name": payment_intent.beneficiary_name,
                "document": payment_intent.beneficiary_document,
                "account_ref": payment_intent.beneficiary_account_ref,
            },
            "references": {
                "provider_intent_id": payment_intent.provider_intent_id,
                "provider_reference": payment_intent.provider_reference,
                "provider_cus": payment_intent.provider_cus,
            },
            "pricing": {
                "pricing_snapshot": dict(payment_intent.pricing_snapshot or {}),
                "fee_breakdown": dict(payment_intent.fee_breakdown or {}),
                "tax_breakdown": dict(payment_intent.tax_breakdown or {}),
            },
            "destination_payload": dict(payment_intent.destination_payload or {}),
            "provider_payload": self.build_provider_payload(payment_intent),
        }

    def build_provider_payload(self, payment_intent) -> dict[str, Any]:
        return {
            "reference": payment_intent.external_reference or payment_intent.internal_reference,
            "amount": str(payment_intent.amount),
            "currency": payment_intent.currency,
            "beneficiary_name": payment_intent.beneficiary_name,
            "beneficiary_document": payment_intent.beneficiary_document,
            "beneficiary_account_ref": payment_intent.beneficiary_account_ref,
            "invoice_reference": payment_intent.invoice_reference,
            "metadata": {
                "payment_intent_id": str(payment_intent.pk),
                "internal_reference": payment_intent.internal_reference,
            },
        }

    def verify_callback(self, payload: dict, headers: dict | None = None) -> bool:
        callback_signature = dict(self.provider_contract().get("callback_contract", {}).get("signature") or {})
        strategy = str(callback_signature.get("strategy") or "hmac_sha256_body").strip().lower()
        if strategy in {"none", "unsigned"}:
            return True
        secret_setting_key = str(callback_signature.get("secret_setting_key") or "callback_secret").strip()
        provider_settings = self.provider_settings()
        secret = str(provider_settings.get(secret_setting_key) or "").strip()
        if not secret and isinstance(provider_settings.get("callback_auth"), dict):
            secret = str(provider_settings.get("callback_auth", {}).get("secret") or "").strip()
        if not secret:
            return bool(callback_signature.get("allow_unsigned_when_secret_missing", True))
        header_name = str(callback_signature.get("header") or "X-Vexxo-Provider-Signature").strip()
        provided = _get_header_value(headers, header_name)
        body = json.dumps(payload or {}, sort_keys=True, default=str).encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return bool(provided) and hmac.compare_digest(provided, expected)

    def normalize_callback(self, payload: dict, headers: dict | None = None) -> dict[str, Any]:
        normalized = extract_contract_callback_fields(self.provider_code, payload or {})
        identifiers = [
            str(normalized.get("payment_intent_id") or "").strip(),
            str(normalized.get("provider_intent_id") or "").strip(),
            str(normalized.get("external_reference") or "").strip(),
            str(normalized.get("provider_reference") or "").strip(),
        ]
        if not any(identifiers):
            raise PaymentProviderContractError(
                "El callback no trae ningun identificador resoluble para PaymentIntent.",
                code="missing_callback_identifier",
            )
        meaningful_state = [
            str(normalized.get("status") or "").strip(),
            str(normalized.get("issue_kind") or "").strip(),
            str(normalized.get("settlement_reference") or "").strip(),
        ]
        if not any(meaningful_state):
            raise PaymentProviderContractError(
                "El callback no trae estado, issue_kind ni settlement_reference.",
                code="missing_callback_state",
            )
        signature_valid = self.verify_callback(payload, headers=headers)
        normalized["signature_valid"] = signature_valid
        return normalized


class GenericPaymentProviderAdapter(BasePaymentProviderAdapter):
    provider_code = "generic"


class WompiPaymentProviderAdapter(BasePaymentProviderAdapter):
    provider_code = "wompi"

    def build_provider_payload(self, payment_intent) -> dict[str, Any]:
        payload = super().build_provider_payload(payment_intent)
        return {
            "reference": payload["reference"],
            "amount_in_cents": int((Decimal(str(payment_intent.amount)) * Decimal("100")).quantize(Decimal("1"))),
            "currency": payment_intent.currency,
            "customer_data": {
                "full_name": payment_intent.beneficiary_name,
                "legal_id": payment_intent.beneficiary_document,
            },
            "payment_method": {
                "type": payment_intent.rail,
                "extra": {
                    "account_ref": payment_intent.beneficiary_account_ref,
                    "invoice_reference": payment_intent.invoice_reference,
                },
            },
            "metadata": payload["metadata"],
        }


ADAPTERS = {
    "generic": GenericPaymentProviderAdapter,
    "wompi": WompiPaymentProviderAdapter,
}


def get_payment_provider_adapter(provider: str) -> BasePaymentProviderAdapter:
    provider_code = str(provider or "").strip().lower() or "generic"
    adapter_cls = ADAPTERS.get(provider_code, GenericPaymentProviderAdapter)
    return adapter_cls()
