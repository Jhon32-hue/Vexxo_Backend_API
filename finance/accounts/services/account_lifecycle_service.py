"""
Casos de uso de lifecycle del agregado `Account`.

Descripcion general:
- concentra mutaciones de negocio sobre creacion, cierre, freeze, archive,
  primary y recalc de balance

Analisis detallado:
- estos servicios encapsulan la combinacion correcta de mutacion del agregado y
  emision de eventos `accounts.*`
- la vista los invoca para orquestar sin duplicar builders de payload ni reglas
  de publicacion
"""

from __future__ import annotations

from finance.accounts.domain.events import AccountDomainEventTypes, build_account_lifecycle_payload
from finance.accounts.services.outbox_service import (
    publish_account_balance_updated,
    publish_account_event,
    publish_account_lifecycle_event,
)


def create_account(account):
    account.ensure_owner_membership()
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_CREATED,
        payload=build_account_lifecycle_payload(account=account, change="created"),
        metadata={"source": "accounts.views.perform_create"},
    )


def update_account(*, account, before: dict, after: dict):
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
        payload=build_account_lifecycle_payload(
            account=account,
            change="updated",
            before=before,
            after=after,
        ),
        metadata={"source": "accounts.views.perform_update"},
    )


def close_account_from_delete(account):
    account.close(commit=True, reason="deleted_from_api")
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_CLOSED,
        payload=build_account_lifecycle_payload(
            account=account,
            change="deleted_from_api",
            extra={"final_balance": str(account.balance), "reason": "deleted_from_api"},
        ),
        metadata={"source": "accounts.views.perform_destroy"},
    )


def set_account_primary(account):
    account.set_as_primary()
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
        payload=build_account_lifecycle_payload(
            account=account,
            change="set_primary",
            extra={"is_primary": True},
        ),
        metadata={"source": "accounts.views.set_primary"},
    )
    publish_account_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_PRIMARY_CHANGED,
        payload=build_account_lifecycle_payload(
            account=account,
            change="primary_changed",
            extra={"is_primary": True},
        ),
        metadata={"source": "accounts.views.set_primary"},
    )


def recalc_account_balance(*, account, reason: str):
    old_balance = account.balance
    new_balance = account.recalc_balance(reason=reason)
    publish_account_balance_updated(
        account=account,
        old_balance=old_balance,
        new_balance=new_balance,
        reason=reason,
        metadata={"source": "accounts.views.recalc_balance"},
    )
    publish_account_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_RECALCULATED,
        payload=build_account_lifecycle_payload(
            account=account,
            change="recalculated",
            extra={
                "old_balance": str(old_balance),
                "new_balance": str(new_balance),
                "reason": reason,
            },
        ),
        metadata={"source": "accounts.views.recalc_balance"},
    )
    return {"old_balance": old_balance, "new_balance": new_balance}


def freeze_account(*, account, reason: str):
    account.freeze(reason=reason)
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
        payload=build_account_lifecycle_payload(
            account=account,
            change="freeze",
            extra={"reason": reason},
        ),
        metadata={"source": "accounts.views.freeze"},
    )
    publish_account_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_FROZEN,
        payload=build_account_lifecycle_payload(
            account=account,
            change="frozen",
            extra={"reason": reason},
        ),
        metadata={"source": "accounts.views.freeze"},
    )


def unfreeze_account(account):
    account.unfreeze()
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
        payload=build_account_lifecycle_payload(account=account, change="unfreeze"),
        metadata={"source": "accounts.views.unfreeze"},
    )
    publish_account_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_UNFROZEN,
        payload=build_account_lifecycle_payload(account=account, change="unfrozen"),
        metadata={"source": "accounts.views.unfreeze"},
    )


def archive_account(*, account, reason: str):
    account.archive()
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
        payload=build_account_lifecycle_payload(
            account=account,
            change="archive",
            extra={"reason": reason},
        ),
        metadata={"source": "accounts.views.archive"},
    )
    publish_account_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_ARCHIVED,
        payload=build_account_lifecycle_payload(
            account=account,
            change="archived",
            extra={"reason": reason},
        ),
        metadata={"source": "accounts.views.archive"},
    )


def unarchive_account(account):
    account.unarchive()
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
        payload=build_account_lifecycle_payload(account=account, change="unarchive"),
        metadata={"source": "accounts.views.unarchive"},
    )
    publish_account_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_UNARCHIVED,
        payload=build_account_lifecycle_payload(account=account, change="unarchived"),
        metadata={"source": "accounts.views.unarchive"},
    )


def close_account(*, account, reason: str):
    final_balance = account.close(reason=reason)
    publish_account_lifecycle_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_CLOSED,
        payload=build_account_lifecycle_payload(
            account=account,
            change="closed",
            extra={"final_balance": str(final_balance), "reason": reason},
        ),
        metadata={"source": "accounts.views.close_account"},
    )
    return final_balance
