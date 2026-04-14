from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from finance.transactions.Models.transacciones import Transaction
from finance.transactions.transaction_intake_service import receive_single_intake_row


PARSER_VERSION = "transactions.message_parser.v1"

_INCOME_KEYWORDS = (
    "abono",
    "consignacion",
    "deposito",
    "recibido",
    "recibida",
    "ingreso",
)
_EXPENSE_KEYWORDS = (
    "compra",
    "pago",
    "debito",
    "retiro",
    "cargo",
    "consumo",
)
_TRANSFER_KEYWORDS = (
    "transferencia",
    "transfer",
    "envio",
)


@dataclass
class ParsedMessageTransaction:
    amount: Decimal | None
    currency: str
    tx_type: str
    description: str
    merchant_name: str
    counterparty_name: str
    confidence_score: int


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _extract_currency(text: str, fallback: str = "") -> str:
    upper = text.upper()
    for code in ("COP", "USD", "EUR", "MXN", "CLP", "PEN", "ARS"):
        if code in upper:
            return code
    if "$" in text:
        return (fallback or "COP").upper()
    return (fallback or "").upper()


def _parse_decimal_fragment(fragment: str) -> Decimal | None:
    raw = str(fragment or "").strip()
    if not raw:
        return None
    cleaned = re.sub(r"[^\d,.\-]", "", raw)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        last_comma = cleaned.rfind(",")
        last_dot = cleaned.rfind(".")
        if last_comma > last_dot:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        right = cleaned.split(",")[-1]
        cleaned = cleaned.replace(",", ".") if len(right) <= 2 else cleaned.replace(",", "")
    elif "." in cleaned:
        right = cleaned.split(".")[-1]
        cleaned = cleaned if len(right) <= 2 else cleaned.replace(".", "")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _extract_amount(text: str) -> Decimal | None:
    patterns = [
        r"(?i)(?:por|de|valor|monto|importe)\s*[:\-]?\s*(?:cop|usd|eur|mxn|clp|pen|ars)?\s*\$?\s*([\d.,]+)",
        r"(?i)(?:cop|usd|eur|mxn|clp|pen|ars)\s*\$?\s*([\d.,]+)",
        r"\$\s*([\d.,]+)",
        r"(?<!\d)([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|[\d]+(?:[.,]\d{2}))(?!\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            amount = _parse_decimal_fragment(match.group(1))
            if amount is not None and amount > 0:
                return amount
    return None


def _infer_type(text: str, explicit_type: str = "") -> str:
    if explicit_type in Transaction.Type.values:
        return explicit_type
    lowered = text.lower()
    if any(keyword in lowered for keyword in _TRANSFER_KEYWORDS):
        if "recib" in lowered or "entrada" in lowered:
            return Transaction.Type.INCOME
        if "envio" in lowered or "salida" in lowered:
            return Transaction.Type.EXPENSE
        return Transaction.Type.TRANSFER
    if any(keyword in lowered for keyword in _INCOME_KEYWORDS):
        return Transaction.Type.INCOME
    if any(keyword in lowered for keyword in _EXPENSE_KEYWORDS):
        return Transaction.Type.EXPENSE
    return Transaction.Type.EXPENSE


def _extract_named_party(text: str, patterns: tuple[str, ...]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = _normalize_spaces(match.group(1))
            value = re.split(r"[.!,;]| saldo| disponible| ref\b| referencia\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
            return value[:160]
    return ""


def _extract_merchant_name(text: str) -> str:
    return _extract_named_party(
        text,
        (
            r"(?:compra|pago|consumo|cargo)\s+(?:en|a)\s+([A-Za-z0-9 _\-.&]+)",
            r"(?:establecimiento|comercio)\s*[:\-]?\s*([A-Za-z0-9 _\-.&]+)",
        ),
    )


def _extract_counterparty_name(text: str) -> str:
    return _extract_named_party(
        text,
        (
            r"(?:transferencia|abono|deposito|consignacion)\s+(?:de|desde)\s+([A-Za-z0-9 _\-.&]+)",
            r"(?:para|a favor de)\s+([A-Za-z0-9 _\-.&]+)",
        ),
    )


def _build_description(text: str, merchant_name: str, counterparty_name: str, tx_type: str, explicit_description: str = "") -> str:
    if explicit_description:
        return _normalize_spaces(explicit_description)[:255]
    if merchant_name:
        prefix = "Compra en" if tx_type == Transaction.Type.EXPENSE else "Movimiento en"
        return f"{prefix} {merchant_name}"[:255]
    if counterparty_name:
        prefix = "Ingreso de" if tx_type == Transaction.Type.INCOME else "Transferencia con"
        return f"{prefix} {counterparty_name}"[:255]
    return _normalize_spaces(text)[:255]


def _compute_confidence(*, amount: Decimal | None, tx_type: str, merchant_name: str, counterparty_name: str, explicit_hints: bool) -> int:
    score = 35
    if amount is not None:
        score += 30
    if tx_type in Transaction.Type.values:
        score += 15
    if merchant_name or counterparty_name:
        score += 10
    if explicit_hints:
        score += 10
    return max(0, min(100, score))


def parse_message_transaction(
    *,
    text: str,
    currency: str = "",
    explicit_type: str = "",
    explicit_description: str = "",
    explicit_amount: Decimal | None = None,
) -> ParsedMessageTransaction:
    normalized_text = _normalize_spaces(text)
    merchant_name = _extract_merchant_name(normalized_text)
    counterparty_name = _extract_counterparty_name(normalized_text)
    amount = explicit_amount if explicit_amount is not None else _extract_amount(normalized_text)
    tx_type = _infer_type(normalized_text, explicit_type=explicit_type)
    description = _build_description(
        normalized_text,
        merchant_name=merchant_name,
        counterparty_name=counterparty_name,
        tx_type=tx_type,
        explicit_description=explicit_description,
    )
    detected_currency = _extract_currency(normalized_text, fallback=currency)
    confidence = _compute_confidence(
        amount=amount,
        tx_type=tx_type,
        merchant_name=merchant_name,
        counterparty_name=counterparty_name,
        explicit_hints=bool(explicit_type or explicit_description or explicit_amount is not None),
    )
    return ParsedMessageTransaction(
        amount=amount,
        currency=detected_currency,
        tx_type=tx_type,
        description=description,
        merchant_name=merchant_name,
        counterparty_name=counterparty_name,
        confidence_score=confidence,
    )


def receive_message_intake(
    *,
    provider: str,
    source: str,
    provider_account_id: str = "",
    account_id=None,
    internal_account_id=None,
    message_id: str,
    sender_id: str = "",
    received_at,
    text: str,
    request_id: str,
    idempotency_key: str,
    currency: str = "",
    amount: Decimal | None = None,
    date=None,
    tx_type: str = "",
    description: str = "",
    raw_payload: dict | None = None,
    metadata: dict | None = None,
):
    parsed = parse_message_transaction(
        text=text,
        currency=currency,
        explicit_type=tx_type,
        explicit_description=description,
        explicit_amount=amount,
    )
    if parsed.amount is None:
        raise ValueError("No se pudo inferir el monto del mensaje. Envia amount explicito o mejora el parser.")
    received_at_dt = received_at
    if timezone.is_naive(received_at_dt):
        received_at_dt = timezone.make_aware(received_at_dt, timezone.get_current_timezone())
    row = {
        "account_id": account_id,
        "internal_account_id": internal_account_id,
        "external_id": str(message_id),
        "provider_event_id": str(message_id),
        "provider_status": "inferred_pending_confirmation",
        "type": parsed.tx_type,
        "status": Transaction.Status.PENDING,
        "amount": str(parsed.amount),
        "date": str(date or received_at_dt.date()),
        "currency": parsed.currency,
        "description": parsed.description,
        "notes": _normalize_spaces(text),
        "confirmed": False,
        "affects_balance": True,
        "rail": Transaction.Rail.MESSAGE,
        "channel": Transaction.Channel.SMS if source == "sms" else Transaction.Channel.EMAIL if source == "email" else Transaction.Channel.MESSAGE_INFERRED,
        "data_origin": Transaction.DataOrigin.INFERRED,
        "confidence_score": parsed.confidence_score,
        "message_id": str(message_id),
        "sender_id": str(sender_id or ""),
        "received_at": received_at_dt.isoformat(),
        "parsed_text": _normalize_spaces(text),
        "parser_version": PARSER_VERSION,
        "needs_user_confirmation": True,
        "inference_status": "needs_confirmation",
        "merchant_name": parsed.merchant_name,
        "counterparty_name": parsed.counterparty_name,
        "raw_payload": raw_payload or {},
        "metadata": {
            "parser": PARSER_VERSION,
            "source_hint": source,
            **(metadata or {}),
        },
    }
    return receive_single_intake_row(
        provider=provider,
        source=source,
        provider_account_id=provider_account_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        row=row,
    )

