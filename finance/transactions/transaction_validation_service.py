from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from rest_framework import serializers

from finance.accounts.models import Account
from finance.accounts.services.permission_service import (
    account_scope_for_user,
    user_can_post_transactions,
    user_can_view_account,
)
from finance.transactions.Models.transacciones import ScheduledPayment, Tag, Transaction
from finance.transactions.utils_limits import account_month_expense_total, user_month_tx_count
from identity.users.domain.plan_matrix import get_plan_capabilities


def assert_owner(user, obj, field: str) -> None:
    if obj and getattr(obj, "owner_id", None) and obj.owner_id != user.id:
        raise serializers.ValidationError({field: "No pertenece al usuario autenticado."})


def visible_accounts_for_user(user):
    return account_scope_for_user(user, Account.objects.all())


def transaction_scope_for_user(user, queryset):
    if not user or not user.is_authenticated:
        return queryset.none()
    return queryset.filter(account__in=visible_accounts_for_user(user)).distinct()


def scheduled_payment_scope_for_user(user, queryset):
    if not user or not user.is_authenticated:
        return queryset.none()
    return queryset.filter(Q(owner=user) | Q(account__in=visible_accounts_for_user(user))).distinct()


def participant_scope_for_user(user, queryset):
    if not user or not user.is_authenticated:
        return queryset.none()
    return queryset.filter(transaction__account__in=visible_accounts_for_user(user)).distinct()


def resolve_transaction_ledger_owner(*, user, account, instance=None):
    if account:
        if not user_can_post_transactions(user, account):
            raise serializers.ValidationError({"account": "No tienes permisos para registrar transacciones en esta cuenta."})
        return account.owner
    if instance is not None:
        account = getattr(instance, "account", None)
        if account and not user_can_view_account(user, account):
            raise serializers.ValidationError({"account": "No tienes acceso a la cuenta de esta transaccion."})
        return getattr(instance, "owner", user)
    return user


def assert_ledger_owner(owner, obj, field: str) -> None:
    if obj and getattr(obj, "owner_id", None) and obj.owner_id != owner.id:
        raise serializers.ValidationError({field: "No pertenece al ledger de la cuenta seleccionada."})


def validate_transaction_payload(*, user, attrs: dict, instance=None) -> dict:
    amount = attrs.get("amount", getattr(instance, "amount", None))
    if amount is None or Decimal(amount) <= 0:
        raise serializers.ValidationError({"amount": "El monto debe ser mayor a 0."})

    account = attrs.get("account", getattr(instance, "account", None))
    ledger_owner = resolve_transaction_ledger_owner(user=user, account=account, instance=instance)

    for field in [
        "category",
        "vendor",
        "income_source",
        "debt",
        "installment",
        "scheduled_payment",
        "payment_intent",
    ]:
        assert_ledger_owner(ledger_owner, attrs.get(field) or getattr(instance, field, None), field)

    tx_type = attrs.get("type", getattr(instance, "type", None))
    date = attrs.get("date", getattr(instance, "date", None))
    category = attrs.get("category", getattr(instance, "category", None))
    income_source = attrs.get("income_source", getattr(instance, "income_source", None))
    debt = attrs.get("debt", getattr(instance, "debt", None))
    installment = attrs.get("installment", getattr(instance, "installment", None))
    scheduled_payment = attrs.get("scheduled_payment", getattr(instance, "scheduled_payment", None))

    if category and hasattr(category, "type"):
        if tx_type == Transaction.Type.EXPENSE and category.type != "expense":
            raise serializers.ValidationError({"category": "La categoria debe ser de gasto."})
        if tx_type == Transaction.Type.INCOME and category.type != "income":
            raise serializers.ValidationError({"category": "La categoria debe ser de ingreso."})

    if income_source and tx_type != Transaction.Type.INCOME:
        raise serializers.ValidationError(
            {"income_source": "Solo puedes asociar una fuente de ingreso a transacciones de tipo 'income'."}
        )

    if (debt or installment) and tx_type != Transaction.Type.EXPENSE:
        raise serializers.ValidationError(
            {"debt": "Las deudas/cuotas solo deben asociarse a transacciones de gasto."}
        )

    if installment and not debt:
        if hasattr(installment, "debt") and installment.debt:
            attrs["debt"] = installment.debt
        else:
            raise serializers.ValidationError({"installment": "La cuota debe estar asociada a una deuda valida."})

    if debt and installment and getattr(installment, "debt_id", None) != debt.id:
        raise serializers.ValidationError({"installment": "La cuota no pertenece a la deuda seleccionada."})

    if scheduled_payment and getattr(scheduled_payment, "status", None) == ScheduledPayment.Status.PAID:
        raise serializers.ValidationError({"scheduled_payment": "Este pago programado ya esta marcado como pagado."})

    is_reimbursable = attrs.get("is_reimbursable", getattr(instance, "is_reimbursable", False))
    if is_reimbursable and tx_type != Transaction.Type.EXPENSE:
        raise serializers.ValidationError({"is_reimbursable": "Solo los gastos pueden ser reembolsables."})

    if tx_type == Transaction.Type.EXPENSE and account and date:
        monthly_limit = getattr(account, "monthly_expense_limit", None)
        lock_on_limit = getattr(account, "lock_on_limit", False)
        if monthly_limit:
            month_total = account_month_expense_total(account, date)
            projected = month_total + Decimal(amount)
            if projected > Decimal(monthly_limit) and lock_on_limit:
                raise serializers.ValidationError({"amount": "Limite mensual de gasto para la cuenta excedido."})

    if instance is None and user and date:
        max_monthly_tx = get_plan_capabilities(getattr(user, "plan", "free")).get("max_monthly_tx_per_account")
        if max_monthly_tx is not None:
            current_count = user_month_tx_count(ledger_owner, date)
            if current_count >= max_monthly_tx:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": (
                            "Has alcanzado el maximo de transacciones permitidas "
                            f"en este mes para tu plan ({max_monthly_tx})."
                        )
                    }
                )

    parent = attrs.get("parent", getattr(instance, "parent", None))
    if parent and parent.parent_id:
        raise serializers.ValidationError({"parent": "No puedes anidar splits a mas de un nivel."})

    return attrs


def apply_tag_selection(tx: Transaction, tags_data) -> Transaction:
    if isinstance(tags_data, list):
        tx.tags.set(Tag.objects.filter(owner=tx.owner, id__in=tags_data))
    return tx
