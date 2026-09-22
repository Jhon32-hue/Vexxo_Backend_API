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
import requests

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


class PaymentProviderUnavailable(PaymentProviderContractError):
    def __init__(self, message: str = "El proveedor no esta configurado para dispatch."):
        super().__init__(message, code="provider_unavailable")


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

    def dispatch(self, payment_intent, *, ephemeral_payload: dict[str, Any]) -> dict[str, Any]:
        raise PaymentProviderUnavailable()

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
            return bool(callback_signature.get("allow_unsigned_when_secret_missing", False))
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

    def dispatch(self, payment_intent, *, ephemeral_payload: dict[str, Any]) -> dict[str, Any]:
        provider_settings = self.provider_settings()
        private_key = str(provider_settings.get("private_key") or "").strip()
        integrity_secret = str(provider_settings.get("integrity_secret") or "").strip()
        base_url = str(provider_settings.get("base_url") or "").strip().rstrip("/")
        if not private_key or not integrity_secret or not base_url:
            raise PaymentProviderUnavailable()
        provider_payload = self.build_provider_payload(payment_intent)
        reference = provider_payload["reference"]
        amount_in_cents = provider_payload["amount_in_cents"]
        currency = provider_payload["currency"]
        payment_method = dict(ephemeral_payload.get("payment_method") or {})
        customer_email = str(ephemeral_payload.get("customer_email") or "").strip()
        acceptance_token = str(ephemeral_payload.get("acceptance_token") or "").strip()
        if not payment_method or not customer_email or not acceptance_token:
            raise PaymentProviderContractError(
                "Wompi requiere payment_method, customer_email y acceptance_token.",
                code="missing_dispatch_fields",
            )
        integrity_signature = hashlib.sha256(
            f"{reference}{amount_in_cents}{currency}{integrity_secret}".encode("utf-8")
        ).hexdigest()
        body = {
            **provider_payload,
            "customer_email": customer_email,
            "acceptance_token": acceptance_token,
            "payment_method": payment_method,
            "signature": integrity_signature,
        }
        try:
            response = requests.post(
                f"{base_url}/transactions",
                json=body,
                headers={"Authorization": f"Bearer {private_key}", "Content-Type": "application/json"},
                timeout=15,
            )
            response_data = response.json() if response.content else {}
        except (requests.RequestException, ValueError) as exc:
            raise PaymentProviderContractError(
                "Wompi no respondio con un contrato valido.", code="provider_transport_error"
            ) from exc
        if not response.ok:
            error_type = str((response_data.get("error") or {}).get("type") or f"http_{response.status_code}")
            raise PaymentProviderContractError("Wompi rechazo el dispatch.", code=error_type[:64])
        transaction = dict(response_data.get("data") or {})
        status = str(transaction.get("status") or "PENDING").strip().lower()
        return {
            "provider_intent_id": str(transaction.get("id") or "")[:128],
            "provider_reference": str(transaction.get("reference") or reference)[:128],
            "status": status,
            "metadata": {
                "provider_status": status,
                "redirect_url": str(transaction.get("redirect_url") or "")[:1000],
                "payment_method_type": str(payment_method.get("type") or "")[:64],
            },
        }

    def verify_callback(self, payload: dict, headers: dict | None = None) -> bool:
        secret = str(self.provider_settings().get("events_secret") or "").strip()
        signature = dict((payload or {}).get("signature") or {})
        properties = signature.get("properties") or []
        timestamp = signature.get("timestamp")
        provided = str(signature.get("checksum") or _get_header_value(headers, "X-Event-Checksum") or "").strip()
        if not secret or not properties or timestamp in (None, "") or not provided:
            return False
        values: list[str] = []
        for path in properties:
            current: Any = payload
            for part in str(path).split("."):
                if not isinstance(current, dict) or part not in current:
                    return False
                current = current[part]
            values.append(str(current))
        expected = hashlib.sha256(("".join(values) + str(timestamp) + secret).encode("utf-8")).hexdigest()
        return hmac.compare_digest(expected, provided)


class LocalFakePaymentProviderAdapter(BasePaymentProviderAdapter):
    """Deterministic local PSP. It never performs network or stores payment secrets."""

    provider_code = "local_fake"

    def dispatch(self, payment_intent, *, ephemeral_payload: dict[str, Any]) -> dict[str, Any]:
        if not bool(getattr(settings, "PAYMENTS_LOCAL_FAKE_ENABLED", False)):
            raise PaymentProviderUnavailable("El proveedor local_fake solo esta habilitado explicitamente en local.")
        scenario = str((ephemeral_payload or {}).get("scenario") or "processing").strip().lower()
        allowed = {"processing", "succeeded", "failed", "requires_action", "timeout"}
        if scenario not in allowed:
            raise PaymentProviderContractError("Escenario local_fake no soportado.", code="invalid_fake_scenario")
        if scenario == "timeout":
            raise PaymentProviderContractError("Timeout determinista de local_fake.", code="provider_timeout")
        digest = hashlib.sha256(f"local_fake:{payment_intent.pk}".encode("utf-8")).hexdigest()[:24]
        metadata = {"scenario": scenario, "deterministic": True}
        if scenario == "requires_action":
            metadata["redirect_url"] = f"vexxo-local://payments/{payment_intent.pk}/confirm"
        return {
            "provider_intent_id": f"lf_{digest}",
            "provider_reference": f"local-{digest}",
            "status": scenario,
            "metadata": metadata,
        }


ADAPTERS = {
    "generic": GenericPaymentProviderAdapter,
    "wompi": WompiPaymentProviderAdapter,
    "local_fake": LocalFakePaymentProviderAdapter,
    "local-stub": LocalFakePaymentProviderAdapter,
}


def get_payment_provider_adapter(provider: str) -> BasePaymentProviderAdapter:
    provider_code = str(provider or "").strip().lower() or "generic"
    adapter_cls = ADAPTERS.get(provider_code, GenericPaymentProviderAdapter)
    return adapter_cls()
