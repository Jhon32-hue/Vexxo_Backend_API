"""
Servicios de inteligencia derivada para accounts.

Descripcion general:
- recalcula snapshots, read models y senales derivadas a partir del estado
  actual de las cuentas del usuario
- convierte el dominio operativo de `accounts` en una capa de lectura util para
  onboarding, segmentacion, soporte y partnerships

Analisis detallado:
- estas proyecciones viven dentro del mismo bounded context porque se derivan
  exclusivamente del modulo de cuentas y no requieren aun un pipeline externo
- el servicio puede ejecutarse por demanda desde API o reaccionando a eventos
  del propio modulo
- la intencion es que Vexxo tenga una lectura consolidada del usuario sin
  recalcular distribuciones, señales o segmentos en cada endpoint

Que se puede hacer despues:
- historizar snapshots por fecha
- exportar estos resultados a BigQuery o feature stores
- mezclar senales con transacciones, goals o budgets en otro nivel de dominio
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from finance.accounts.models import (
    Account,
    AccountCurrencyExposure,
    AccountDataOrigin,
    AccountOwnerMetrics,
    AccountOwnership,
    AccountPortfolioSnapshot,
    AccountProductSignal,
    AccountRiskSnapshot,
    AccountStatus,
    AccountType,
    AccountTypeDistribution,
    AccountVerificationLevel,
)

User = get_user_model()

ZERO = Decimal("0.00")
RATIO_PLACES = Decimal("0.001")
MONEY_PLACES = Decimal("0.01")
IDLE_DAYS = 30
STALE_INVITE_DAYS = 14
SMALL_ACCOUNT_THRESHOLD = Decimal("100.00")
INVESTMENT_TYPES = {
    AccountType.INVESTMENT,
    AccountType.BROKERAGE,
    AccountType.RETIREMENT,
    AccountType.CRYPTO,
}
CREDIT_TYPES = {AccountType.CREDIT, AccountType.LOAN}
LIQUID_TYPES = {
    AccountType.CASH,
    AccountType.BANK,
    AccountType.SAVINGS,
    AccountType.WALLET,
    AccountType.PREPAID,
}


def _quantize_ratio(value: Decimal) -> Decimal:
    return Decimal(value).quantize(RATIO_PLACES)


def _quantize_money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_PLACES)


def _ratio(numerator: int | Decimal, denominator: int | Decimal) -> Decimal:
    denominator_value = Decimal(str(denominator or 0))
    if denominator_value <= ZERO:
        return Decimal("0.000")
    numerator_value = Decimal(str(numerator or 0))
    return _quantize_ratio(numerator_value / denominator_value)


def _percentage(numerator: int | Decimal, denominator: int | Decimal) -> Decimal:
    return _quantize_ratio(_ratio(numerator, denominator) * Decimal("100"))


def _score(raw_value: int | float | Decimal) -> int:
    return max(0, min(100, int(raw_value)))


def _resolve_user(user_or_id) -> User | None:
    if isinstance(user_or_id, User):
        return user_or_id
    if not user_or_id:
        return None
    return User.objects.filter(pk=user_or_id).first()


def _account_base_balance(account: Account) -> Decimal:
    if account.base_currency and account.virtual_balance_base is not None:
        return Decimal(account.virtual_balance_base)
    return Decimal(account.balance)


def _serialize_decimal_map(values: dict[str, Decimal]) -> dict[str, str]:
    return {key: str(_quantize_money(value)) for key, value in values.items()}


def _portfolio_segment(*, total_accounts: int, has_shared: bool, has_investment: bool, currencies_count: int, has_credit: bool) -> str:
    if has_shared and has_investment:
        return "vida_financiera_colaborativa"
    if has_investment:
        return "expuesto_inversion"
    if total_accounts >= 4 or currencies_count > 1:
        return "multi_cuenta_avanzado"
    if has_credit:
        return "organizador_basico"
    return "starter_financiero"


def _build_product_signals(*, portfolio: AccountPortfolioSnapshot, risk: AccountRiskSnapshot, now):
    signals: list[dict] = []

    if portfolio.active_accounts >= 3:
        signals.append(
            {
                "signal_code": "ready_for_multi_account_upgrade",
                "signal_value": {"active_accounts": portfolio.active_accounts},
                "confidence": 82,
                "evidence": {
                    "active_accounts": portfolio.active_accounts,
                    "currencies_count": portfolio.currencies_count,
                },
            }
        )

    if not portfolio.has_investment_exposure and portfolio.active_accounts >= 2 and portfolio.external_accounts >= 1:
        signals.append(
            {
                "signal_code": "ready_for_investment_offer",
                "signal_value": {"eligible": True},
                "confidence": 71,
                "evidence": {
                    "external_accounts": portfolio.external_accounts,
                    "active_accounts": portfolio.active_accounts,
                },
            }
        )

    if risk.is_credit_ready_candidate:
        signals.append(
            {
                "signal_code": "ready_for_credit_precheck",
                "signal_value": {"eligible": True, "segment": risk.segment_label},
                "confidence": 76,
                "evidence": {
                    "portfolio_stability_score": risk.portfolio_stability_score,
                    "sync_reliability_score": risk.sync_reliability_score,
                },
            }
        )

    if not portfolio.counts_by_type.get(AccountType.BANK, 0) and (
        portfolio.counts_by_type.get(AccountType.WALLET, 0) or portfolio.counts_by_type.get(AccountType.CASH, 0)
    ):
        signals.append(
            {
                "signal_code": "needs_basic_bank_product",
                "signal_value": {"eligible": True},
                "confidence": 80,
                "evidence": {
                    "wallet_accounts": portfolio.counts_by_type.get(AccountType.WALLET, 0),
                    "cash_accounts": portfolio.counts_by_type.get(AccountType.CASH, 0),
                },
            }
        )

    if portfolio.has_multi_currency_accounts:
        signals.append(
            {
                "signal_code": "likely_international_user",
                "signal_value": {"eligible": True},
                "confidence": 74,
                "evidence": {"currencies_count": portfolio.currencies_count},
            }
        )

    if portfolio.has_shared_financial_behavior:
        signals.append(
            {
                "signal_code": "high_shared_finance_behavior",
                "signal_value": {"eligible": True},
                "confidence": 78,
                "evidence": {
                    "shared_accounts": portfolio.shared_accounts,
                    "observed_accounts": portfolio.observed_accounts,
                },
            }
        )

    if portfolio.has_recurrent_sync_failures or portfolio.idle_accounts_ratio >= Decimal("0.500"):
        signals.append(
            {
                "signal_code": "needs_manual_finance_support",
                "signal_value": {"eligible": True},
                "confidence": 69,
                "evidence": {
                    "has_recurrent_sync_failures": portfolio.has_recurrent_sync_failures,
                    "idle_accounts_ratio": str(portfolio.idle_accounts_ratio),
                },
            }
        )

    if not portfolio.has_goal_oriented_accounts and portfolio.active_accounts >= 2:
        signals.append(
            {
                "signal_code": "ready_for_goal_vault_offer",
                "signal_value": {"eligible": True},
                "confidence": 65,
                "evidence": {"active_accounts": portfolio.active_accounts},
            }
        )

    for signal in signals:
        signal["source"] = "accounts"
        signal["expires_at"] = now + timedelta(days=30)

    return signals


@transaction.atomic
def refresh_account_intelligence_for_user(user_or_id) -> dict | None:
    user = _resolve_user(user_or_id)
    if user is None:
        return None

    accounts = list(
        Account.objects.filter(owner=user)
        .prefetch_related("memberships")
        .order_by("created_at")
    )

    now = timezone.now()
    total_accounts = len(accounts)
    total_base_abs = ZERO
    total_base_balance = ZERO
    latest_reconciled_at = None
    latest_drift_at = None
    idle_threshold = now - timedelta(days=IDLE_DAYS)

    counts_by_type = Counter()
    counts_by_currency = Counter()
    ownership_distribution = Counter()
    balances_by_currency: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)

    active_accounts = 0
    primary_accounts = 0
    shared_accounts = 0
    observed_accounts = 0
    external_accounts = 0
    investment_accounts = 0
    credit_accounts = 0
    frozen_accounts = 0
    archived_accounts = 0
    closed_accounts = 0
    idle_accounts = 0
    small_accounts = 0
    healthy_sync_accounts = 0
    verified_accounts = 0
    reconciled_accounts = 0
    liquid_balance_total = ZERO
    volatile_balance_total = ZERO

    primary_account = None
    max_dependency_abs = ZERO
    average_age_total_days = Decimal("0.00")

    for account in accounts:
        counts_by_type[account.type] += 1
        counts_by_currency[account.currency] += 1
        ownership_distribution[account.ownership] += 1

        account_balance_base = _account_base_balance(account)
        account_balance_abs = abs(account_balance_base)
        total_base_balance += account_balance_base
        total_base_abs += account_balance_abs
        balances_by_currency[account.currency] += Decimal(account.balance)
        max_dependency_abs = max(max_dependency_abs, account_balance_abs)

        age_days = max(0, (now - account.created_at).days)
        average_age_total_days += Decimal(age_days)

        if account.status == AccountStatus.ACTIVE:
            active_accounts += 1
        elif account.status == AccountStatus.FROZEN:
            frozen_accounts += 1
        elif account.status == AccountStatus.ARCHIVED:
            archived_accounts += 1
        elif account.status == AccountStatus.CLOSED:
            closed_accounts += 1

        if account.is_primary and primary_account is None:
            primary_account = account
        if account.is_primary and account.status == AccountStatus.ACTIVE:
            primary_accounts += 1

        if account.ownership == AccountOwnership.SHARED:
            shared_accounts += 1
        if account.ownership == AccountOwnership.OBSERVED:
            observed_accounts += 1

        if account.has_external_link:
            external_accounts += 1
        if account.sync_health == "healthy":
            healthy_sync_accounts += 1

        if account.type in INVESTMENT_TYPES:
            investment_accounts += 1
            volatile_balance_total += account_balance_abs
        if account.type in CREDIT_TYPES:
            credit_accounts += 1
        if account.type in LIQUID_TYPES:
            liquid_balance_total += max(account_balance_base, ZERO)

        if account.goal_amount and Decimal(account.goal_amount) > ZERO or account.role == "goal_vault":
            pass

        if (account.last_activity_at or account.created_at) < idle_threshold:
            idle_accounts += 1
        if account_balance_abs <= SMALL_ACCOUNT_THRESHOLD:
            small_accounts += 1

        if account.verification_level in {
            AccountVerificationLevel.EXTERNALLY_VERIFIED,
            AccountVerificationLevel.RECONCILED,
        }:
            verified_accounts += 1
        if account.verification_level == AccountVerificationLevel.RECONCILED:
            reconciled_accounts += 1

        if account.last_consistent_snapshot_at and (
            latest_reconciled_at is None or account.last_consistent_snapshot_at > latest_reconciled_at
        ):
            latest_reconciled_at = account.last_consistent_snapshot_at
        if account.last_drift_detected_at and (
            latest_drift_at is None or account.last_drift_detected_at > latest_drift_at
        ):
            latest_drift_at = account.last_drift_detected_at

    currencies_count = len(counts_by_currency)
    has_goal_oriented_accounts = any(
        (account.goal_amount and Decimal(account.goal_amount) > ZERO) or account.role == "goal_vault"
        for account in accounts
    )
    has_recurrent_sync_failures = any(
        account.has_external_link and (account.sync_status == "error" or int(account.sync_attempts or 0) >= 3)
        for account in accounts
    )

    avg_account_age_days = _quantize_money(
        average_age_total_days / Decimal(total_accounts)
    ) if total_accounts else ZERO
    idle_ratio = _ratio(idle_accounts, total_accounts)
    frozen_ratio = _ratio(frozen_accounts, total_accounts)
    archived_ratio = _ratio(archived_accounts, total_accounts)
    closed_ratio = _ratio(closed_accounts, total_accounts)
    dependency_ratio = _ratio(max_dependency_abs, total_base_abs)
    volatile_ratio = _ratio(volatile_balance_total, total_base_abs)
    sync_success_ratio = _ratio(healthy_sync_accounts, external_accounts)

    portfolio_complexity_score = _score(
        total_accounts * 8
        + max(0, currencies_count - 1) * 12
        + (15 if shared_accounts or observed_accounts else 0)
        + (15 if investment_accounts else 0)
        + (10 if credit_accounts else 0)
        + min(external_accounts * 5, 20)
    )
    account_diversification_score = _score(
        len([key for key, value in counts_by_type.items() if value]) * 12
        + max(0, currencies_count - 1) * 18
        + (10 if shared_accounts else 0)
        + (12 if investment_accounts else 0)
        + (10 if credit_accounts else 0)
    )

    portfolio_snapshot, _ = AccountPortfolioSnapshot.objects.update_or_create(
        owner=user,
        defaults={
            "primary_account": primary_account,
            "total_accounts": total_accounts,
            "active_accounts": active_accounts,
            "primary_accounts": primary_accounts,
            "shared_accounts": shared_accounts,
            "observed_accounts": observed_accounts,
            "external_accounts": external_accounts,
            "investment_accounts": investment_accounts,
            "credit_accounts": credit_accounts,
            "frozen_accounts": frozen_accounts,
            "archived_accounts": archived_accounts,
            "closed_accounts": closed_accounts,
            "idle_accounts": idle_accounts,
            "currencies_count": currencies_count,
            "total_cached_balance_in_base": _quantize_money(total_base_balance),
            "counts_by_type": dict(counts_by_type),
            "counts_by_currency": dict(counts_by_currency),
            "balances_by_currency": _serialize_decimal_map(dict(balances_by_currency)),
            "ownership_distribution": dict(ownership_distribution),
            "has_multi_currency_accounts": currencies_count > 1,
            "has_external_linked_accounts": external_accounts > 0,
            "has_investment_exposure": investment_accounts > 0,
            "has_credit_products": credit_accounts > 0,
            "has_shared_financial_behavior": (shared_accounts + observed_accounts) > 0,
            "has_goal_oriented_accounts": has_goal_oriented_accounts,
            "has_recurrent_sync_failures": has_recurrent_sync_failures,
            "has_idle_accounts": idle_accounts > 0,
            "has_many_small_accounts": small_accounts >= 3,
            "has_single_dependency_account": dependency_ratio >= Decimal("0.800"),
            "avg_account_age_days": avg_account_age_days,
            "idle_accounts_ratio": idle_ratio,
            "frozen_accounts_ratio": frozen_ratio,
            "archived_accounts_ratio": archived_ratio,
            "closed_accounts_ratio": closed_ratio,
            "portfolio_complexity_score": portfolio_complexity_score,
            "account_diversification_score": account_diversification_score,
            "last_reconciled_at": latest_reconciled_at,
        },
    )

    AccountOwnerMetrics.objects.update_or_create(
        owner=user,
        defaults={
            "total_accounts": total_accounts,
            "active_accounts": active_accounts,
            "primary_accounts": primary_accounts,
            "shared_accounts": shared_accounts,
            "observed_accounts": observed_accounts,
            "external_accounts": external_accounts,
            "investment_accounts": investment_accounts,
            "credit_accounts": credit_accounts,
            "currencies_count": currencies_count,
            "total_cached_balance_in_base": _quantize_money(total_base_balance),
            "last_reconciled_at": latest_reconciled_at,
        },
    )

    AccountCurrencyExposure.objects.filter(owner=user).delete()
    currency_rows = []
    for currency, count in counts_by_currency.items():
        estimated_balance = abs(balances_by_currency.get(currency, ZERO))
        currency_rows.append(
            AccountCurrencyExposure(
                owner=user,
                currency=currency,
                accounts_count=count,
                estimated_total_balance=_quantize_money(estimated_balance),
                exposure_percentage=_percentage(estimated_balance, total_base_abs),
            )
        )
    if currency_rows:
        AccountCurrencyExposure.objects.bulk_create(currency_rows)

    AccountTypeDistribution.objects.filter(owner=user).delete()
    type_totals: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    for account in accounts:
        type_totals[account.type] += abs(_account_base_balance(account))

    type_rows = []
    for account_type, count in counts_by_type.items():
        total_balance = type_totals.get(account_type, ZERO)
        type_rows.append(
            AccountTypeDistribution(
                owner=user,
                account_type=account_type,
                accounts_count=count,
                total_balance=_quantize_money(total_balance),
                exposure_percentage=_percentage(total_balance, total_base_abs),
            )
        )
    if type_rows:
        AccountTypeDistribution.objects.bulk_create(type_rows)

    product_mix_score = _score(
        (20 if counts_by_type.get(AccountType.BANK, 0) else 0)
        + (20 if counts_by_type.get(AccountType.WALLET, 0) or counts_by_type.get(AccountType.CASH, 0) else 0)
        + (20 if credit_accounts else 0)
        + (20 if investment_accounts else 0)
        + (20 if currencies_count > 1 else 0)
    )
    portfolio_stability_score = _score(
        100
        - int(closed_ratio * Decimal("40"))
        - int(frozen_ratio * Decimal("35"))
        - int(archived_ratio * Decimal("20"))
        - int(idle_ratio * Decimal("15"))
        + min(int(avg_account_age_days // Decimal("30")) * 2, 10)
    )
    external_verification_score = _score(_percentage(verified_accounts, total_accounts))
    ownership_complexity_score = _score(shared_accounts * 20 + observed_accounts * 15 + (10 if shared_accounts else 0))
    liquidity_proxy_score = _score(_percentage(liquid_balance_total, total_base_abs))
    sync_reliability_score = _score(_percentage(healthy_sync_accounts, external_accounts))

    segment_label = _portfolio_segment(
        total_accounts=total_accounts,
        has_shared=portfolio_snapshot.has_shared_financial_behavior,
        has_investment=portfolio_snapshot.has_investment_exposure,
        currencies_count=currencies_count,
        has_credit=portfolio_snapshot.has_credit_products,
    )
    is_credit_ready_candidate = (
        active_accounts >= 2
        and external_accounts >= 1
        and portfolio_stability_score >= 60
        and sync_reliability_score >= 60
        and not has_recurrent_sync_failures
    )

    risk_snapshot, _ = AccountRiskSnapshot.objects.update_or_create(
        owner=user,
        defaults={
            "product_mix_score": product_mix_score,
            "portfolio_stability_score": portfolio_stability_score,
            "sync_reliability_score": sync_reliability_score,
            "external_verification_score": external_verification_score,
            "ownership_complexity_score": ownership_complexity_score,
            "liquidity_proxy_score": liquidity_proxy_score,
            "active_credit_accounts": credit_accounts,
            "active_investment_accounts": investment_accounts,
            "external_linked_accounts": external_accounts,
            "dependency_ratio": dependency_ratio,
            "sync_success_ratio": sync_success_ratio,
            "volatile_exposure_ratio": volatile_ratio,
            "is_credit_ready_candidate": is_credit_ready_candidate,
            "segment_label": segment_label,
            "supporting_factors": {
                "portfolio_complexity_score": portfolio_complexity_score,
                "account_diversification_score": account_diversification_score,
                "latest_reconciled_at": latest_reconciled_at.isoformat() if latest_reconciled_at else None,
                "latest_drift_at": latest_drift_at.isoformat() if latest_drift_at else None,
            },
        },
    )

    desired_signals = _build_product_signals(portfolio=portfolio_snapshot, risk=risk_snapshot, now=now)
    desired_codes = {item["signal_code"] for item in desired_signals}
    existing_signals = {
        signal.signal_code: signal
        for signal in AccountProductSignal.objects.filter(owner=user)
    }

    for signal_data in desired_signals:
        defaults = {
            "signal_value": signal_data["signal_value"],
            "confidence": signal_data["confidence"],
            "source": signal_data["source"],
            "evidence": signal_data["evidence"],
            "expires_at": signal_data["expires_at"],
            "is_active": True,
            "generated_at": now,
        }
        AccountProductSignal.objects.update_or_create(
            owner=user,
            signal_code=signal_data["signal_code"],
            defaults=defaults,
        )

    if existing_signals:
        AccountProductSignal.objects.filter(owner=user).exclude(signal_code__in=desired_codes).update(
            is_active=False,
            expires_at=now,
        )

    return {
        "portfolio_snapshot": portfolio_snapshot,
        "risk_snapshot": risk_snapshot,
        "product_signals": list(AccountProductSignal.objects.filter(owner=user, is_active=True).order_by("signal_code")),
        "owner_metrics": AccountOwnerMetrics.objects.get(owner=user),
        "currency_exposures": list(AccountCurrencyExposure.objects.filter(owner=user).order_by("currency")),
        "type_distributions": list(AccountTypeDistribution.objects.filter(owner=user).order_by("account_type")),
    }


def refresh_account_intelligence_for_account(account: Account | int | str) -> dict | None:
    if isinstance(account, Account):
        return refresh_account_intelligence_for_user(account.owner_id)

    account_obj = Account.objects.filter(pk=account).only("owner_id").first()
    if account_obj is None:
        return None
    return refresh_account_intelligence_for_user(account_obj.owner_id)
