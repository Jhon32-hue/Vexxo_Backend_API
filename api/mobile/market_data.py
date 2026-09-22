from __future__ import annotations

from datetime import timedelta
from dataclasses import dataclass
from decimal import Decimal

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    name: str
    kind: str
    currency: str
    price: str
    change_percent: str
    source: str


FRANKFURTER_URL = "https://api.frankfurter.dev/v2/rates"
COINGECKO_SIMPLE_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_MARKET_CHART_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
CACHE_KEY = "api.mobile.markets.v1"
CACHE_SECONDS = 60 * 20
DEFAULT_HISTORY_DAYS = 7


def build_mobile_market_snapshot(*, base_currency: str = "COP") -> dict:
    """Small BFF snapshot for mobile. Financial data is informational only."""
    normalized_base = (base_currency or "COP").upper()
    cached = cache.get(f"{CACHE_KEY}.{normalized_base}")
    if cached:
        return cached

    fx = _fetch_frankfurter_fx(base_currency=normalized_base)
    snapshot = {
        "base_currency": fx["base_currency"],
        "provider": fx["provider"],
        "provider_status": fx["provider_status"],
        "as_of": fx["as_of"],
        "updated_at": timezone.now().isoformat(),
        "refresh_hint_seconds": CACHE_SECONDS,
        "fx_pairs": fx["pairs"],
        "watchlist": _market_watchlist(),
        "series": _market_series(base_currency=fx["base_currency"], pairs=fx["pairs"]),
        "disclaimer": "Datos informativos. No son recomendacion financiera ni fuente contable.",
    }
    cache.set(f"{CACHE_KEY}.{normalized_base}", snapshot, CACHE_SECONDS)
    return snapshot


def _fetch_frankfurter_fx(*, base_currency: str) -> dict:
    provider_status = "fallback"
    provider = "local_fallback"
    as_of = ""
    pairs = _fallback_fx_pairs(base_currency)
    frankfurter_base = base_currency if base_currency in {"USD", "EUR", "GBP"} else "USD"
    try:
        response = requests.get(
            FRANKFURTER_URL,
            params={"base": frankfurter_base, "quotes": "COP,USD,EUR,GBP,BRL,MXN"},
            timeout=getattr(settings, "MOBILE_MARKET_DATA_TIMEOUT_SECONDS", 2.5),
        )
        response.raise_for_status()
        payload = response.json()
        rates = _latest_rates_from_frankfurter(payload)
        if isinstance(rates, dict) and rates:
            provider_status = "live"
            provider = "frankfurter"
            as_of = _latest_frankfurter_date(payload)
            pairs = _pairs_from_rates(base=frankfurter_base, rates=rates)
    except requests.RequestException:
        pass
    return {
        "base_currency": frankfurter_base,
        "provider": provider,
        "provider_status": provider_status,
        "as_of": as_of,
        "pairs": pairs,
    }


def _pairs_from_rates(*, base: str, rates: dict) -> list[dict]:
    rows = []
    for quote in ["COP", "EUR", "GBP", "BRL", "MXN"]:
        if quote == base:
            continue
        rate = _decimal_text(rates.get(quote))
        if rate:
            rows.append(
                {
                    "base": base,
                    "quote": quote,
                    "rate": rate,
                    "inverse_rate": _inverse_text(rate),
                    "source": "frankfurter",
                }
            )
    return rows


def _fallback_fx_pairs(base_currency: str) -> list[dict]:
    base = "USD" if base_currency not in {"USD", "EUR", "GBP"} else base_currency
    rows = [
        ("USD", "COP", "4100"),
        ("USD", "EUR", "0.92"),
        ("USD", "GBP", "0.78"),
        ("USD", "MXN", "18.1"),
        ("USD", "BRL", "5.4"),
    ]
    return [
        {
            "base": source,
            "quote": quote,
            "rate": rate,
            "inverse_rate": _inverse_text(rate),
            "source": "local_fallback",
        }
        for source, quote, rate in rows
        if source == base
    ]


def _static_watchlist() -> list[dict]:
    quotes = [
        MarketQuote("USD/COP", "Dolar estadounidense", "fx", "COP", "4100", "+0.2%", "fx"),
        MarketQuote("EUR/USD", "Euro", "fx", "USD", "1.08", "-0.1%", "fx"),
        MarketQuote("BTC", "Bitcoin", "crypto", "USD", "64000", "+1.4%", "reference"),
        MarketQuote("ETH", "Ethereum", "crypto", "USD", "3200", "+0.8%", "reference"),
        MarketQuote("AAPL", "Apple", "stock", "USD", "220", "+0.5%", "reference"),
        MarketQuote("NU", "Nubank", "stock", "USD", "12", "+0.9%", "reference"),
    ]
    return [quote.__dict__ for quote in quotes]


def _market_watchlist() -> list[dict]:
    rows = []
    rows.extend(_fetch_crypto_watchlist())
    rows.extend(_static_equity_watchlist())
    if not rows:
        return _static_watchlist()
    return rows


def _market_series(*, base_currency: str, pairs: list[dict]) -> list[dict]:
    rows = []
    primary_pair = next(
        (
            pair for pair in pairs
            if pair.get("base") == base_currency and pair.get("quote") in {"COP", "USD", "EUR"}
        ),
        pairs[0] if pairs else None,
    )
    if primary_pair:
        rows.append(
            _fx_pair_series(
                base=primary_pair.get("base", base_currency),
                quote=primary_pair.get("quote", "COP"),
            )
        )
    rows.extend(_crypto_market_series())
    return rows


def _fx_pair_series(*, base: str, quote: str) -> dict:
    fallback = {
        "id": f"{base}/{quote}",
        "label": f"{base}/{quote}",
        "kind": "fx",
        "currency": quote,
        "source": "local_fallback",
        "points": _fallback_fx_series(base=base, quote=quote),
    }
    today = timezone.now().date()
    start_date = today - timedelta(days=DEFAULT_HISTORY_DAYS - 1)
    try:
        response = requests.get(
            FRANKFURTER_URL,
            params={
                "base": base,
                "quotes": quote,
                "from": start_date.isoformat(),
                "to": today.isoformat(),
            },
            timeout=getattr(settings, "MOBILE_MARKET_DATA_TIMEOUT_SECONDS", 2.5),
        )
        response.raise_for_status()
        payload = response.json()
        rates = _timeseries_from_frankfurter(payload)
        points = []
        if isinstance(rates, dict):
            for date_key, day_rates in sorted(rates.items()):
                if not isinstance(day_rates, dict):
                    continue
                value = _decimal_text(day_rates.get(quote))
                if not value:
                    continue
                points.append({"x": str(date_key), "y": value})
        if points:
            return {
                **fallback,
                "source": "frankfurter",
                "points": points,
            }
    except requests.RequestException:
        pass
    return fallback


def _crypto_market_series() -> list[dict]:
    rows = []
    for coin_id, symbol, name in [
        ("bitcoin", "BTC", "Bitcoin"),
        ("ethereum", "ETH", "Ethereum"),
    ]:
        rows.append(_single_crypto_series(coin_id=coin_id, symbol=symbol, name=name))
    return rows


def _single_crypto_series(*, coin_id: str, symbol: str, name: str) -> dict:
    fallback = {
        "id": symbol,
        "label": name,
        "kind": "crypto",
        "currency": "USD",
        "source": "local_fallback",
        "points": _fallback_crypto_series(symbol=symbol),
    }
    try:
        response = requests.get(
            COINGECKO_MARKET_CHART_URL.format(coin_id=coin_id),
            params={"vs_currency": "usd", "days": DEFAULT_HISTORY_DAYS, "interval": "daily"},
            timeout=getattr(settings, "MOBILE_MARKET_DATA_TIMEOUT_SECONDS", 2.5),
        )
        response.raise_for_status()
        payload = response.json()
        prices = payload.get("prices") if isinstance(payload, dict) else None
        points = []
        if isinstance(prices, list):
            for index, row in enumerate(prices):
                if not isinstance(row, list) or len(row) < 2:
                    continue
                points.append(
                    {
                        "x": (timezone.now().date() - timedelta(days=max(0, DEFAULT_HISTORY_DAYS - index - 1))).isoformat(),
                        "y": _decimal_text(row[1]),
                    }
                )
        if points:
            return {
                **fallback,
                "source": "coingecko",
                "points": points,
            }
    except requests.RequestException:
        pass
    return fallback


def _fetch_crypto_watchlist() -> list[dict]:
    try:
        response = requests.get(
            COINGECKO_SIMPLE_PRICE_URL,
            params={
                "ids": "bitcoin,ethereum",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            timeout=getattr(settings, "MOBILE_MARKET_DATA_TIMEOUT_SECONDS", 2.5),
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return [
            MarketQuote("BTC", "Bitcoin", "crypto", "USD", "64000", "+1.4%", "reference").__dict__,
            MarketQuote("ETH", "Ethereum", "crypto", "USD", "3200", "+0.8%", "reference").__dict__,
        ]

    mapping = [
        ("bitcoin", "BTC", "Bitcoin"),
        ("ethereum", "ETH", "Ethereum"),
    ]
    rows = []
    for key, symbol, name in mapping:
        row = payload.get(key) if isinstance(payload, dict) else {}
        if not isinstance(row, dict):
            continue
        price = _decimal_text(row.get("usd"))
        if not price:
            continue
        change = _percent_text(row.get("usd_24h_change"))
        rows.append(
            MarketQuote(
                symbol=symbol,
                name=name,
                kind="crypto",
                currency="USD",
                price=price,
                change_percent=change,
                source="coingecko",
            ).__dict__
        )
    return rows


def _static_equity_watchlist() -> list[dict]:
    # Until a licensed market-data provider is configured, equities remain visual references.
    return [
        MarketQuote("AAPL", "Apple", "stock", "USD", "220", "+0.5%", "reference").__dict__,
        MarketQuote("NU", "Nubank", "stock", "USD", "12", "+0.9%", "reference").__dict__,
    ]


def _latest_rates_from_frankfurter(payload) -> dict:
    if isinstance(payload, dict):
        rates = payload.get("rates")
        return rates if isinstance(rates, dict) else {}
    if isinstance(payload, list):
        rows = {}
        for row in payload:
            if not isinstance(row, dict):
                continue
            quote = str(row.get("quote") or "").upper()
            rate = row.get("rate")
            if quote and rate is not None:
                rows[quote] = rate
        return rows
    return {}


def _latest_frankfurter_date(payload) -> str:
    if isinstance(payload, dict):
        return str(payload.get("date") or "")
    if isinstance(payload, list) and payload:
        date_values = [
            str(row.get("date") or "")
            for row in payload
            if isinstance(row, dict) and row.get("date")
        ]
        return max(date_values) if date_values else ""
    return ""


def _timeseries_from_frankfurter(payload) -> dict:
    if isinstance(payload, dict):
        rates = payload.get("rates")
        return rates if isinstance(rates, dict) else {}
    if isinstance(payload, list):
        rows = {}
        for row in payload:
            if not isinstance(row, dict):
                continue
            date_key = str(row.get("date") or "")
            quote = str(row.get("quote") or "").upper()
            rate = row.get("rate")
            if not date_key or not quote or rate is None:
                continue
            rows.setdefault(date_key, {})[quote] = rate
        return rows
    return {}


def _decimal_text(value) -> str:
    try:
        decimal = Decimal(str(value))
        text = format(decimal.normalize(), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    except Exception:
        return ""


def _percent_text(value) -> str:
    try:
        decimal = Decimal(str(value)).quantize(Decimal("0.01"))
        sign = "+" if decimal >= 0 else ""
        return f"{sign}{decimal}%"
    except Exception:
        return "0%"


def _inverse_text(value: str) -> str:
    try:
        decimal = Decimal(value)
        if decimal == 0:
            return ""
        return str((Decimal("1") / decimal).quantize(Decimal("0.000001")))
    except Exception:
        return ""


def _fallback_fx_series(*, base: str, quote: str) -> list[dict]:
    anchor = {
        ("USD", "COP"): Decimal("4100"),
        ("USD", "EUR"): Decimal("0.92"),
        ("USD", "GBP"): Decimal("0.78"),
        ("USD", "MXN"): Decimal("18.1"),
        ("USD", "BRL"): Decimal("5.4"),
    }.get((base, quote), Decimal("1"))
    pattern = [Decimal("-0.8"), Decimal("-0.3"), Decimal("0.2"), Decimal("0.5"), Decimal("0.1"), Decimal("0.7"), Decimal("0")]
    today = timezone.now().date()
    points = []
    for index, drift in enumerate(pattern):
        date_key = today - timedelta(days=len(pattern) - index - 1)
        value = anchor * (Decimal("1") + (drift / Decimal("100")))
        points.append({"x": date_key.isoformat(), "y": _decimal_text(value)})
    return points


def _fallback_crypto_series(*, symbol: str) -> list[dict]:
    anchor = {
        "BTC": Decimal("64000"),
        "ETH": Decimal("3200"),
    }.get(symbol, Decimal("100"))
    pattern = [Decimal("-2.1"), Decimal("1.2"), Decimal("-0.6"), Decimal("0.8"), Decimal("1.6"), Decimal("-0.4"), Decimal("2.2")]
    today = timezone.now().date()
    points = []
    for index, drift in enumerate(pattern):
        date_key = today - timedelta(days=len(pattern) - index - 1)
        value = anchor * (Decimal("1") + (drift / Decimal("100")))
        points.append({"x": date_key.isoformat(), "y": _decimal_text(value)})
    return points
