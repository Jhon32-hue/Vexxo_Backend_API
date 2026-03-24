"""
Enums y constantes ligeras del dominio de accounts.

Descripcion general:
- concentra vocabulario pequeno pero transversal del modulo
- evita strings sueltos en models, servicios, signals y vistas

Analisis detallado:
- `AccountMembershipRole` y `AccountAccessMode` definen la gramatica base de
  colaboracion sobre cuentas compartidas
- `BalanceChangeReason` no pretende modelar todos los motivos del sistema,
  sino los motivos operativos minimos que hoy producen cambios de balance en el
  cache contable
- mantener estas piezas juntas ayuda a que `accounts.domain` sea la interfaz
  canonica del modulo frente al resto del backend

Que se puede hacer despues:
- versionar razones mas finas para importaciones, ajustes o syncs externos
- agregar enums de salud operativa si el modulo expone contratos externos
"""

from django.db import models


class AccountMembershipRole(models.TextChoices):
    VIEWER = "viewer", "Viewer"
    MEMBER = "member", "Member"
    ADMIN = "admin", "Admin"
    OWNER = "owner", "Owner"


class AccountAccessMode(models.TextChoices):
    READ_ONLY = "read_only", "Read only"
    WATCH_ONLY = "watch_only", "Watch only"
    FULL = "full", "Full"


class BalanceChangeReason:
    """
    Motivos de cambio de balance emitidos por el flujo contable de accounts.
    """

    TX_CREATED = "tx_created"
    TX_MOVED = "tx_moved"
    TX_UPDATED = "tx_updated"
    TX_DELETED = "tx_deleted"
    TX_FALLBACK_RECALC = "tx_fallback_recalc"
