"""
Permisos y alcance de lectura para el dominio de accounts.

Descripcion general:
- centraliza reglas de acceso para cuentas propias y compartidas
- expone helpers reutilizables por views, serializers y servicios

Analisis detallado:
- Vexxo distingue entre propiedad directa (`owner`) y acceso compartido via
  `AccountMembership`; este modulo evita duplicar esa logica
- la idea es que las vistas no conozcan detalles internos de pesos de rol,
  flags efectivos o compatibilidad legacy
- `account_scope_for_user()` define el universo de cuentas visibles para un
  usuario autenticado
- `user_can_manage_account_settings()` y `user_can_manage_members()` separan
  permisos operativos importantes: administrar configuracion de la cuenta y
  administrar colaboradores

Que se puede hacer despues:
- mover aqui reglas mas finas de limites por plan o producto
- agregar politicas por contexto social (`shared_scope_type`) si Vexxo decide
  que grupos o metas puedan imponer restricciones adicionales
"""

from __future__ import annotations

from django.db.models import Q

from finance.accounts.domain.enums import AccountAccessMode, AccountMembershipRole


ROLE_WEIGHT = {
    AccountMembershipRole.VIEWER: 10,
    AccountMembershipRole.MEMBER: 20,
    AccountMembershipRole.ADMIN: 30,
    AccountMembershipRole.OWNER: 40,
}


def membership_for_user(user, account):
    if not user or not user.is_authenticated:
        return None
    if not account or not getattr(account, "pk", None):
        return None

    prefetched = getattr(account, "_prefetched_objects_cache", {})
    memberships = prefetched.get("memberships")
    if memberships is not None:
        for membership in memberships:
            if membership.user_id == user.id and membership.is_active:
                return membership
        return None

    return account.memberships.filter(user=user, is_active=True).first()


def user_can_view_account(user, account) -> bool:
    if not user or not user.is_authenticated:
        return False
    if account.owner_id == user.id:
        return True
    return membership_for_user(user, account) is not None


def user_can_post_transactions(user, account) -> bool:
    if not user or not user.is_authenticated:
        return False
    if account.owner_id == user.id:
        return not account.read_only

    membership = membership_for_user(user, account)
    if not membership:
        return False

    if membership.access_mode in (AccountAccessMode.WATCH_ONLY, AccountAccessMode.READ_ONLY):
        return False
    return bool(getattr(membership, "effective_can_post_transactions", membership.can_post_transactions))


def user_can_manage_members(user, account) -> bool:
    if not user or not user.is_authenticated:
        return False
    if account.owner_id == user.id:
        return True

    membership = membership_for_user(user, account)
    if not membership:
        return False

    if getattr(membership, "effective_can_manage_members", False):
        return True
    return ROLE_WEIGHT.get(membership.role, 0) >= ROLE_WEIGHT[AccountMembershipRole.ADMIN]


def user_can_manage_account_settings(user, account) -> bool:
    if not user or not user.is_authenticated:
        return False
    if account.owner_id == user.id:
        return True

    membership = membership_for_user(user, account)
    if not membership:
        return False

    if getattr(membership, "effective_can_manage_account_settings", False):
        return True
    return ROLE_WEIGHT.get(membership.role, 0) >= ROLE_WEIGHT[AccountMembershipRole.ADMIN]


def account_scope_for_user(user, queryset):
    """
    Scope de lectura compatible con propiedad directa + memberships activas.
    """
    if not user or not user.is_authenticated:
        return queryset.none()

    return queryset.filter(
        Q(owner=user)
        | Q(memberships__user=user, memberships__is_active=True)
    ).distinct()
