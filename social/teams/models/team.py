from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Team(models.Model):
    """
    Equipo de trabajo / grupo de cuentas compartidas.

    - `owner`: usuario que creó el equipo (tiene control total).
    - `is_personal`: True si es el equipo personal creado automáticamente
      al registrar el usuario.
    """

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="owned_teams",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    is_personal = models.BooleanField(
        default=True,
        help_text="Equipo personal creado automáticamente para el usuario.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Equipo"
        verbose_name_plural = "Equipos"
        ordering = ["created_at"]
        # Evita equipos duplicados con el mismo owner y nombre.
        unique_together = ("owner", "name")

    def __str__(self):
        return self.name

    # -------- Helpers útiles para permisos / lógica de negocio --------
    @property
    def members_count(self) -> int:
        """Número de miembros (incluyendo owner)."""
        return self.memberships.count()

    def is_member(self, user: User) -> bool:
        """Devuelve True si el usuario pertenece al equipo."""
        if not user or not user.is_authenticated:
            return False
        return self.memberships.filter(user=user).exists()

    def is_owner(self, user: User) -> bool:
        """Devuelve True si el usuario es el propietario del equipo."""
        if not user or not user.is_authenticated:
            return False
        return self.owner_id == user.id
