"""
Paquete de serializers de grants.
"""

from .permission_serializers import UserPermissionGrantSerializer, UserPermissionRevokeSerializer

__all__ = ["UserPermissionGrantSerializer", "UserPermissionRevokeSerializer"]
