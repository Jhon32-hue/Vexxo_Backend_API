"""
Paquete de modelos de dispositivos de identidad.

Descripcion general:
- expone el contrato persistente de dispositivos conocidos del usuario
- mantiene la importacion canonica `identity.devices.models`

Analisis detallado:
- esta capa permite reorganizar el modulo sin romper imports existentes
- el modelo concreto vive en `device.py`, pero el resto del sistema puede
  seguir importando desde `identity.devices.models`
"""

from .device import (
    DeviceAttestationStatus,
    DevicePlatformAttestationChallenge,
    DeviceSignatureChallenge,
    DeviceTrustLevel,
    DeviceType,
    UserDevice,
)

__all__ = [
    "DeviceAttestationStatus",
    "DevicePlatformAttestationChallenge",
    "DeviceSignatureChallenge",
    "DeviceTrustLevel",
    "DeviceType",
    "UserDevice",
]
