"""
Paquete de serializers de consentimientos.
"""

from .consent_serializers import (
    UserConsentGrantSerializer,
    UserConsentRevokeSerializer,
    UserConsentSerializer,
)

__all__ = [
    "UserConsentGrantSerializer",
    "UserConsentRevokeSerializer",
    "UserConsentSerializer",
]
