from django.db import models
from django.contrib.auth import get_user_model

from .team import Team

User = get_user_model()


class Membership(models.Model):
    """
    Relación Usuario ↔ Equipo con rol.

    - owner       → controla el equipo (invita, elimina, configura).
    - accountant  → ve y registra movimientos contables.
    - viewer      → solo lectura.
    """

    ROLE_CHOICES = [
        ("owner", "owner"),
        ("accountant", "accountant"),
        ("viewer", "viewer"),
    ]

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="team_memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="viewer",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Permite desactivar miembros sin borrarlos.",
    )

    class Meta:
        verbose_name = "Membresía"
        verbose_name_plural = "Membresías"
        unique_together = ("team", "user")

    def __str__(self):
        return f"{self.user.username} @ {self.team.name} ({self.role})"

    # Helpers para permisos
    def is_owner(self) -> bool:
        return self.role == "owner"

    def is_accountant(self) -> bool:
        return self.role == "accountant"

    def is_viewer(self) -> bool:
        return self.role == "viewer"
