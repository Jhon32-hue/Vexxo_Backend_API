"""
Integracion entre lifecycle de usuario y dominio de cuentas.

Descripcion general:
- adapta eventos de `identity.users` al agregado `Account`
- evita que `identity` tenga que conocer detalles internos del modelo de
  cuentas para onboarding, sync de moneda base o suspensiones operativas

Analisis detallado:
- `identity.users` es el origen del lifecycle del usuario, pero `accounts`
  decide como materializar eso en el espacio financiero del owner
- este servicio crea la cuenta inicial, sincroniza moneda base por defecto y
  ajusta politicas de sync cuando el estado del usuario cambia
"""

from __future__ import annotations

from typing import Iterable

from django.db import transaction

from finance.accounts.domain.events import AccountDomainEventTypes, build_account_lifecycle_payload
from finance.accounts.models import Account, AccountRole, AccountStatus, AccountType, AccountVisibility
from finance.accounts.services.intelligence_dispatch_service import dispatch_account_intelligence_refresh
from finance.accounts.services.outbox_service import publish_account_lifecycle_event


def _publish_account_updated(account: Account, *, change: str, source: str, extra: dict | None = None) -> None:
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
        payload=build_account_lifecycle_payload(
            account=account,
            change=change,
            extra=extra or {},
        ),
        metadata={"source": source},
    )


def _refresh_accounts_intelligence(owner_id, *, source: str) -> None:
    dispatch_account_intelligence_refresh(
        owner_id=owner_id,
        source=source,
        task_name_suffix=f"{owner_id}",
    )


def ensure_user_financial_home(user) -> Account:
    preferred_currency = user.preferred_currency or "COP"
    created = False

    with transaction.atomic():
        account = (
            Account.objects.select_for_update()
            .filter(owner=user)
            .exclude(status=AccountStatus.CLOSED)
            .order_by("-is_primary", "created_at")
            .first()
        )
        if account is None:
            account = Account.objects.create(
                owner=user,
                name="Cuenta principal",
                currency=preferred_currency,
                type=AccountType.SAVINGS,
                role=AccountRole.SPENDING,
                visibility=AccountVisibility.PRIVATE,
                balance="0.00",
                initial_balance="0.00",
                base_currency=preferred_currency,
                institution="Vexxo Starter",
                is_primary=True,
                status=AccountStatus.ACTIVE,
            )
            created = True
        else:
            changed = False
            if not account.is_primary and account.status == AccountStatus.ACTIVE:
                account.is_primary = True
                changed = True
            if not account.base_currency:
                account.base_currency = preferred_currency
                changed = True
            if not account.institution:
                account.institution = "Vexxo Starter"
                changed = True
            if account.name == "":
                account.name = "Cuenta principal"
                changed = True
            if changed:
                account.save(update_fields=["is_primary", "base_currency", "institution", "name", "updated_at"])

    account.ensure_owner_membership()

    if created:
        publish_account_lifecycle_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_CREATED,
            payload=build_account_lifecycle_payload(
                account=account,
                change="created_from_user_registration",
                extra={"origin": "identity.users"},
            ),
            metadata={"source": "accounts.user_integration.ensure_user_financial_home"},
        )
    _refresh_accounts_intelligence(user.pk, source="accounts.user_integration.ensure_user_financial_home")
    return account


def sync_user_currency_to_accounts(*, user, previous_currency: str | None = None) -> int:
    updated_accounts: list[Account] = []
    qs = Account.objects.filter(owner=user).exclude(status=AccountStatus.CLOSED)

    for account in qs:
        current_base = (account.base_currency or "").strip()
        if not current_base or (previous_currency and current_base == previous_currency):
            account.base_currency = user.preferred_currency
            account.save(update_fields=["base_currency", "updated_at"])
            updated_accounts.append(account)

    for account in updated_accounts:
        _publish_account_updated(
            account,
            change="owner_preferred_currency_changed",
            source="accounts.user_integration.sync_user_currency_to_accounts",
            extra={
                "preferred_currency": user.preferred_currency,
                "previous_currency": previous_currency,
            },
        )

    _refresh_accounts_intelligence(user.pk, source="accounts.user_integration.sync_user_currency_to_accounts")
    return len(updated_accounts)


def disable_auto_sync_for_user(user) -> int:
    accounts = list(
        Account.objects.filter(owner=user, allow_auto_sync=True).exclude(provider="").exclude(external_id="")
    )
    for account in accounts:
        account.allow_auto_sync = False
        account.save(update_fields=["allow_auto_sync", "updated_at"])
        _publish_account_updated(
            account,
            change="owner_suspended_auto_sync_disabled",
            source="accounts.user_integration.disable_auto_sync_for_user",
        )
    _refresh_accounts_intelligence(user.pk, source="accounts.user_integration.disable_auto_sync_for_user")
    return len(accounts)


def disable_auto_sync_for_user_provider(*, user, provider: str) -> int:
    provider = str(provider or "").strip()
    if not provider:
        return disable_auto_sync_for_user(user)

    accounts = list(
        Account.objects.filter(
            owner=user,
            allow_auto_sync=True,
            provider__iexact=provider,
        ).exclude(provider="").exclude(external_id="")
    )
    for account in accounts:
        account.allow_auto_sync = False
        account.save(update_fields=["allow_auto_sync", "updated_at"])
        _publish_account_updated(
            account,
            change="consent_revoked_auto_sync_disabled",
            source="accounts.user_integration.disable_auto_sync_for_user_provider",
            extra={"provider": provider},
        )
    _refresh_accounts_intelligence(user.pk, source="accounts.user_integration.disable_auto_sync_for_user_provider")
    return len(accounts)


def revoke_provider_integration_access_for_user(*, user, provider: str = "", legal_reason: str = "consent_revoked") -> dict:
    provider = str(provider or "").strip()
    qs = Account.objects.filter(owner=user).exclude(provider="").exclude(external_id="")
    if provider:
        qs = qs.filter(provider__iexact=provider)

    affected_accounts = list(qs)
    disabled = 0
    for account in affected_accounts:
        metadata = dict(account.provider_metadata or {})
        metadata["integration_access"] = "revoked"
        metadata["integration_revoked_reason"] = legal_reason
        metadata["integration_revoked_at"] = account.updated_at.isoformat() if account.updated_at else None
        account.allow_auto_sync = False
        account.next_sync_at = None
        account.sync_cursor = ""
        account.provider_metadata = metadata
        account.save(
            update_fields=[
                "allow_auto_sync",
                "next_sync_at",
                "sync_cursor",
                "provider_metadata",
                "updated_at",
            ]
        )
        disabled += 1
        _publish_account_updated(
            account,
            change="integration_access_revoked",
            source="accounts.user_integration.revoke_provider_integration_access_for_user",
            extra={
                "provider": account.provider,
                "legal_reason": legal_reason,
            },
        )

    _refresh_accounts_intelligence(user.pk, source="accounts.user_integration.revoke_provider_integration_access_for_user")
    return {
        "user_id": str(user.pk),
        "provider": provider,
        "disabled_accounts": disabled,
        "account_ids": [str(account.pk) for account in affected_accounts],
    }


def refresh_user_accounts_projection(user) -> None:
    _refresh_accounts_intelligence(user.pk, source="accounts.user_integration.refresh_user_accounts_projection")
