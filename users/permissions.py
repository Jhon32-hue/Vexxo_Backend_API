from rest_framework import permissions

class IsSelfOrAdmin(permissions.BasePermission):
    """Permite acceso completo al propio perfil o a administradores."""
    def has_object_permission(self, request, view, obj):
        return obj == request.user or request.user.is_staff
