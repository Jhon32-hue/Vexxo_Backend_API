"""
Exports publicos del dominio de identidad.

Descripcion general:
- reexporta el modelo principal y enums de identidad

Analisis detallado:
- reduce acoplamiento a archivos internos concretos
- permite que serializers, vistas, señales y reglas de negocio importen desde
  un unico punto estable
- si el dominio de identidad crece, este modulo sigue siendo el facade
  publico recomendado para imports internos
"""

from .user import PlanType, User, UserStatus

__all__ = [
    "PlanType",
    "User",
    "UserStatus",
]
