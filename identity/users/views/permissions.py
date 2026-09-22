# users/views/permissions.py
from rest_framework import permissions


class IsSelfOrAdmin(permissions.BasePermission):
    """
    Permite acceso completo al propio perfil o a admins.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        return obj == request.user or request.user.is_staff or request.user.is_superuser


class IsAdminUser(permissions.BasePermission):
    """
    Solo staff / superuser.
    """

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )
