"""
Politicas de negocio del bounded context `accounts`.

Descripcion general:
- centraliza reglas compuestas hoy usadas por serializers, guards, mixins y
  vistas

Analisis detallado:
- este modulo no reemplaza invariantes basicas del modelo
- coordina reglas de producto para que create, update, sharing y lifecycle
  consulten la misma fuente
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from finance.accounts.domain.enums import AccountMembershipRole
from finance.accounts.models import Account, AccountStatus, AccountType, GoalStrategy, SharedScopeType
from identity.users.domain.plan_matrix import get_plan_capabilities, resolve_plan_code
from identity.users.services.product_access_service import raise_plan_limit_error

User = get_user_model()

INVESTMENT_TYPES = {
    AccountType.INVESTMENT,
    AccountType.BROKERAGE,
    AccountType.CRYPTO,
    AccountType.RETIREMENT,
}

COUNTED_PLAN_STATUSES = {
    AccountStatus.ACTIVE,
    AccountStatus.FROZEN,
}

PRIMARY_COUNTED_STATUSES = {
    AccountStatus.ACTIVE,
}

ZERO = Decimal("0.00")


def _limit_error(*, message: str, limit, current, plan: str) -> dict:
    return {
        "code": "plan_limit_exceeded",
        "domain": "plan_limits",
        "message": message,
        "limit": limit,
        "current": current,
        "plan": plan,
        "upgrade_plan": "pro",
    }


def resolve_account_plan(user: User) -> str:
    canonical_plan = getattr(user, "plan", None)
    compatibility_plan = getattr(getattr(user, "settings", None), "plan", None)
    resolved = canonical_plan or compatibility_plan or "free"
    return resolve_plan_code(resolved)


def get_account_plan_limits(user: User) -> dict:
    plan = resolve_account_plan(user)
    capability_snapshot = get_plan_capabilities(plan)
    limits = {
        "max_active_accounts": capability_snapshot.get("max_active_accounts"),
        "max_manual_accounts": capability_snapshot.get("max_manual_accounts", capability_snapshot.get("max_active_accounts")),
        "max_connected_accounts": capability_snapshot.get("max_connected_accounts", capability_snapshot.get("max_api_connections")),
        "max_primary_accounts": capability_snapshot.get("max_primary_accounts"),
        "max_investment_accounts": capability_snapshot.get("max_investment_accounts"),
        "max_members_per_account": capability_snapshot.get("max_members_per_account", capability_snapshot.get("max_shared_accounts")),
    }
    if getattr(user, "max_accounts_override", None) is not None:
        limits["max_active_accounts"] = user.max_accounts_override
        limits["max_manual_accounts"] = user.max_accounts_override
    if getattr(user, "max_api_connections_override", None) is not None:
        limits["max_connected_accounts"] = user.max_api_connections_override
    return {
        "plan": plan,
        **limits,
    }


def get_account_plan_usage(user: User, *, exclude_account_id=None) -> dict:
    base_qs = Account.objects.filter(owner=user, status__in=COUNTED_PLAN_STATUSES)
    if exclude_account_id:
        base_qs = base_qs.exclude(pk=exclude_account_id)
    primary_qs = base_qs.filter(status__in=PRIMARY_COUNTED_STATUSES)
    connected_qs = base_qs.exclude(provider="").exclude(external_id="")
    manual_qs = base_qs.filter(provider="", external_id="")
    return {
        "active_accounts": base_qs.count(),
        "manual_accounts": manual_qs.count(),
        "connected_accounts": connected_qs.count(),
        "active_primary_accounts": primary_qs.filter(is_primary=True).count(),
        "active_investment_accounts": base_qs.filter(type__in=INVESTMENT_TYPES).count(),
        "counted_statuses": sorted(COUNTED_PLAN_STATUSES),
        "primary_counted_statuses": sorted(PRIMARY_COUNTED_STATUSES),
    }


def account_creation_limit_errors(user: User, *, account_type: str) -> dict:
    limits = get_account_plan_limits(user)
    usage = get_account_plan_usage(user)
    errors = {}
    max_manual = limits.get("max_manual_accounts")
    if max_manual is not None and usage["manual_accounts"] >= max_manual:
        errors["plan"] = _limit_error(
            message=f"Tu plan {limits['plan']} permite hasta {max_manual} cuentas manuales activas o congeladas.",
            limit=max_manual,
            current=usage["manual_accounts"],
            plan=limits["plan"],
        )
    max_investment = limits.get("max_investment_accounts")
    if (
        account_type in INVESTMENT_TYPES
        and max_investment is not None
        and usage["active_investment_accounts"] >= max_investment
    ):
        errors["type"] = _limit_error(
            message=f"Tu plan {limits['plan']} permite hasta {max_investment} cuentas de inversion.",
            limit=max_investment,
            current=usage["active_investment_accounts"],
            plan=limits["plan"],
        )
    return errors


def primary_account_limit_errors(user: User, *, exclude_account_id=None) -> dict:
    limits = get_account_plan_limits(user)
    usage = get_account_plan_usage(user, exclude_account_id=exclude_account_id)
    max_primary = limits.get("max_primary_accounts")
    if max_primary is not None and usage["active_primary_accounts"] >= max_primary:
        return {
            "is_primary": _limit_error(
                message=f"Tu plan {limits['plan']} permite hasta {max_primary} cuentas principales activas.",
                limit=max_primary,
                current=usage["active_primary_accounts"],
                plan=limits["plan"],
            )
        }
    return {}


def get_account_plan_snapshot(user: User, *, exclude_account_id=None) -> dict:
    limits = get_account_plan_limits(user)
    usage = get_account_plan_usage(user, exclude_account_id=exclude_account_id)
    return {
        "plan": limits["plan"],
        "limits": {
            "max_active_accounts": limits["max_active_accounts"],
            "max_manual_accounts": limits["max_manual_accounts"],
            "max_connected_accounts": limits["max_connected_accounts"],
            "max_primary_accounts": limits["max_primary_accounts"],
            "max_investment_accounts": limits["max_investment_accounts"],
            "max_members_per_account": limits["max_members_per_account"],
        },
        "usage": usage,
    }


def validate_account_write_payload(*, attrs, instance=None, owner=None):
    name = attrs.get("name", getattr(instance, "name", None))
    currency = attrs.get("currency", getattr(instance, "currency", None))
    if owner and name and currency:
        qs = Account.objects.filter(owner=owner, name=name, currency=currency)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"name": "Ya existe una cuenta con este nombre y moneda para este usuario."}
            )

    if owner and instance is None:
        creation_errors = account_creation_limit_errors(owner, account_type=attrs.get("type", AccountType.BANK))
        if creation_errors:
            raise serializers.ValidationError(creation_errors)

    monthly_limit = attrs.get("monthly_expense_limit", getattr(instance, "monthly_expense_limit", None))
    daily_limit = attrs.get("daily_expense_limit", getattr(instance, "daily_expense_limit", None))
    lock_on_limit = attrs.get("lock_on_limit", getattr(instance, "lock_on_limit", False))
    if lock_on_limit and not any(limit is not None and limit > ZERO for limit in (monthly_limit, daily_limit)):
        raise serializers.ValidationError(
            {"lock_on_limit": "lock_on_limit requiere al menos un limite mayor que cero."}
        )

    goal_amount = attrs.get("goal_amount", getattr(instance, "goal_amount", None))
    goal_deadline = attrs.get("goal_deadline", getattr(instance, "goal_deadline", None))
    goal_strategy = attrs.get("goal_strategy", getattr(instance, "goal_strategy", GoalStrategy.NONE))
    auto_contribute_amount = attrs.get("auto_contribute_amount", getattr(instance, "auto_contribute_amount", None))
    auto_contribute_percent = attrs.get(
        "auto_contribute_percent",
        getattr(instance, "auto_contribute_percent", None),
    )
    if goal_deadline and (goal_amount is None or goal_amount <= ZERO):
        raise serializers.ValidationError(
            {"goal_amount": "Si defines goal_deadline debes definir goal_amount mayor que cero."}
        )
    if goal_strategy == GoalStrategy.NONE and any(
        value not in (None, ZERO, Decimal("0.000")) for value in (auto_contribute_amount, auto_contribute_percent)
    ):
        raise serializers.ValidationError(
            {"goal_strategy": "Si configuras aporte automatico debes elegir una estrategia distinta de none."}
        )

    shared_scope_type = attrs.get("shared_scope_type", getattr(instance, "shared_scope_type", SharedScopeType.NONE))
    shared_scope_id = attrs.get("shared_scope_id", getattr(instance, "shared_scope_id", ""))
    if shared_scope_type == SharedScopeType.NONE:
        attrs["shared_scope_id"] = ""
    elif not (shared_scope_id or "").strip():
        raise serializers.ValidationError(
            {"shared_scope_id": "El shared_scope_id es requerido cuando shared_scope_type no es none."}
        )

    if instance and instance.transactions.exists():
        if "currency" in attrs and attrs["currency"] != instance.currency:
            raise serializers.ValidationError(
                {"currency": "No puedes cambiar la moneda de una cuenta que ya tiene transacciones."}
            )
        if "initial_balance" in attrs and attrs["initial_balance"] != instance.initial_balance:
            raise serializers.ValidationError(
                {"initial_balance": "No puedes cambiar el saldo inicial cuando ya existen transacciones."}
            )
    return attrs


def validate_account_membership_payload(*, attrs, instance=None):
    account = attrs.get("account", getattr(instance, "account", None))
    user = attrs.get("user", getattr(instance, "user", None))
    role = attrs.get("role", getattr(instance, "role", None))
    invited_by = attrs.get("invited_by", getattr(instance, "invited_by", None))
    if not account:
        raise serializers.ValidationError({"account": "La cuenta es requerida."})
    if not user:
        raise serializers.ValidationError({"user": "El usuario es requerido."})

    if instance:
        if "account" in attrs and attrs["account"].pk != instance.account_id:
            raise serializers.ValidationError({"account": "No puedes mover una membresia a otra cuenta."})
        if "user" in attrs and attrs["user"].pk != instance.user_id:
            raise serializers.ValidationError({"user": "No puedes cambiar el usuario de una membresia existente."})

    duplicate_qs = instance.__class__.objects.filter(account=account, user=user) if instance else None
    if duplicate_qs is None:
        from finance.accounts.models import AccountMembership

        duplicate_qs = AccountMembership.objects.filter(account=account, user=user)
    if instance:
        duplicate_qs = duplicate_qs.exclude(pk=instance.pk)
    if duplicate_qs.exists():
        raise serializers.ValidationError({"user": "Ese usuario ya tiene una membresia para esta cuenta."})

    if user.id == account.owner_id and not instance:
        raise serializers.ValidationError(
            {"user": "El owner de la cuenta no debe crearse por este flujo; usa ensure_owner_membership()."}
        )

    if role == AccountMembershipRole.OWNER and user.id != account.owner_id:
        raise serializers.ValidationError({"role": "Solo el owner real de la cuenta puede tener rol owner."})

    if invited_by and user.id == invited_by.id:
        raise serializers.ValidationError({"invited_by": "El usuario invitado no puede invitarse a si mismo."})

    return attrs


def validate_account_can_be_primary(account):
    if account.status != AccountStatus.ACTIVE:
        raise serializers.ValidationError({"detail": "Solo una cuenta activa puede marcarse como principal."})
    limit_errors = primary_account_limit_errors(account.owner, exclude_account_id=account.pk)
    if limit_errors:
        raise serializers.ValidationError(limit_errors)


def validate_account_can_close(account, *, via_delete: bool = False):
    if account.balance != ZERO:
        detail = "No puedes cerrar una cuenta con saldo distinto de cero."
        if via_delete:
            detail = "No puedes cerrar una cuenta con saldo distinto de cero desde DELETE."
        raise serializers.ValidationError({"detail": detail})


def validate_account_external_link_allowed(*, account):
    owner = account.owner
    limits = get_account_plan_limits(owner)
    limit = limits.get("max_connected_accounts")
    if limit is None or account.has_external_link:
        return

    usage = get_account_plan_usage(owner, exclude_account_id=account.pk)
    current = usage["connected_accounts"]
    if current >= limit:
        raise_plan_limit_error(
            user=owner,
            metric="max_connected_accounts",
            current=current,
            limit=limit,
            detail="Puedes conectar mas cuentas reales con Pro.",
            source="accounts.link_external_source",
            permission_code="integrations.multi_connection.enabled",
            extra={"account_id": str(account.pk)},
        )


def get_account_membership_limit_usage(*, account) -> dict:
    from finance.accounts.models import AccountMembership

    qs = AccountMembership.objects.filter(account=account).exclude(user_id=account.owner_id)
    qs = qs.filter(
        Q(is_active=True)
        | Q(
            is_active=False,
            revoked_at__isnull=True,
            invitation_sent_at__isnull=False,
            accepted_at__isnull=True,
        )
    )
    return {"shared_memberships": qs.count()}


def validate_account_members_limit(*, account):
    limits = get_account_plan_limits(account.owner)
    limit = limits.get("max_members_per_account")
    if limit is None:
        return

    usage = get_account_membership_limit_usage(account=account)
    current = usage["shared_memberships"]
    if current >= limit:
        raise_plan_limit_error(
            user=account.owner,
            metric="max_members_per_account",
            current=current,
            limit=limit,
            detail="Con Pro puedes invitar mas personas por cuenta.",
            source="accounts.memberships",
            permission_code="sharing.extended.enabled",
            extra={"account_id": str(account.pk)},
        )


def _normalize_invitation_token(invitation_token) -> str:
    if invitation_token in (None, ""):
        return ""
    if isinstance(invitation_token, UUID):
        return str(invitation_token)
    return str(invitation_token).strip()


def validate_membership_invitation_state(*, membership, action: str, invitation_token=None):
    invitation = membership.current_invitation
    latest_invitation = membership.latest_invitation
    now = timezone.now()
    if action in {"accept", "open"}:
        token_value = _normalize_invitation_token(invitation_token)
        if not token_value:
            raise serializers.ValidationError({"invitation_token": "El invitation_token es requerido."})

        target = invitation
        if target is None and latest_invitation is not None and str(latest_invitation.token) == token_value:
            target = latest_invitation
        elif target is not None and str(target.token) != token_value:
            if latest_invitation is not None and str(latest_invitation.token) == token_value:
                target = latest_invitation
            else:
                raise serializers.ValidationError(
                    {"invitation_token": "El invitation_token no coincide con una invitacion valida."}
                )

        if target is None:
            raise serializers.ValidationError({"detail": "La membresia no tiene una invitacion vigente para aceptar."})
        if target.is_expired and target.status not in {
            target.Status.ACCEPTED,
            target.Status.REVOKED,
            target.Status.EXPIRED,
        }:
            target.expire(commit=True)
            raise serializers.ValidationError({"detail": "La invitacion ya expiro."})
        if target.status in {target.Status.REVOKED, target.Status.EXPIRED}:
            raise serializers.ValidationError({"detail": "La invitacion ya no esta activa."})
        if action == "accept" and target.status == target.Status.ACCEPTED:
            if membership.is_active:
                return {"invitation": target, "already_applied": True}
            raise serializers.ValidationError(
                {"detail": "La invitacion ya fue consumida y la membresia quedo inconsistente."}
            )
        if not target.is_current:
            raise serializers.ValidationError({"detail": "La invitacion ya no es la vigente para esta membresia."})
        if target.expires_at and target.expires_at <= now:
            raise serializers.ValidationError({"detail": "La invitacion ya expiro."})
        return {"invitation": target, "already_applied": False}
    if action == "reissue" and membership.is_active:
        raise serializers.ValidationError({"detail": "No puedes reemitir invitacion sobre una membresia activa."})
    return {"invitation": invitation, "already_applied": False}
