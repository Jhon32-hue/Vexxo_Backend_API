from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

class User(AbstractUser):
    """
    Modelo de usuario.
    Base de autenticación, perfil financiero y conexión a integraciones externas.
    """

    CURRENCY_CHOICES = [
        ("COP", "Peso Colombiano"),
        ("USD", "Dólar Americano"),
        ("EUR", "Euro"),
    ]

    # Datos adicionales
    email = models.EmailField(_("Correo electrónico"), unique=True)
    phone_number = models.CharField(_("Teléfono / WhatsApp"), max_length=20, blank=True, null=True)
    preferred_currency = models.CharField(_("Moneda preferida"), max_length=10, choices=CURRENCY_CHOICES, default="COP")
    whatsapp_connected = models.BooleanField(_("Cuenta WhatsApp vinculada"), default=False)
    photo = models.ImageField(_("Foto de perfil"), upload_to="users/photos/", blank=True, null=True)

    # Flags del sistema
    is_verified = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)
    last_login_ip = models.GenericIPAddressField(_("Última IP de login"), blank=True, null=True)
    last_seen = models.DateTimeField(_("Última actividad"), blank=True, null=True)

    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.username} ({self.email})"

    # Métodos utilitarios
    def mark_seen(self, request=None):
        """Actualiza la última actividad e IP."""
        self.last_seen = timezone.now()
        if request and hasattr(request, "META"):
            self.last_login_ip = request.META.get("REMOTE_ADDR")
        self.save(update_fields=["last_seen", "last_login_ip"])

    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    class Meta:
        verbose_name = _("Usuario")
        verbose_name_plural = _("Usuarios")
        ordering = ["username"]
