from decimal import Decimal

from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class Contact(models.Model):
    class Relationship(models.TextChoices):
        FRIEND = "friend", _("Amiga/o")
        FAMILY = "family", _("Familia")
        COWORKER = "coworker", _("Coworker")
        CLIENT = "client", _("Cliente")
        PARTNER = "partner", _("Pareja / Roommate")
        OTHER = "other", _("Otro")

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="contacts",
        help_text=_("Usuario dueño del registro de este contacto."),
    )

    # Si en algún momento ese contacto se registra como usuario real de Vexxo_app
    linked_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="linked_as_contact",
        help_text=_("Usuario real vinculado a este contacto, si existe."),
    )

    name = models.CharField(
        max_length=120,
        help_text=_("Nombre real del contacto."),
    )
    nickname = models.CharField(
        max_length=60,
        blank=True,
        default="",
        help_text=_("Apodo opcional para mostrar (roomie, socio, etc.)."),
    )
    relationship = models.CharField(
        max_length=20,
        choices=Relationship.choices,
        default=Relationship.OTHER,
    )

    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True, null=True)

    currency = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text=_(
            "Moneda en la que se expresa net_balance; "
            "por defecto, la moneda preferida del usuario."
        ),
    )

    # > 0  → el contacto me debe
    # < 0  → yo le debo al contacto
    net_balance = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_(
            "Saldo neto con este contacto en moneda base del usuario. "
            "Positivo = el contacto te debe; negativo = tú debes al contacto."
        ),
    )

    last_activity_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Última actividad relevante con este contacto."),
    )
    last_transaction_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Fecha/hora de la última transacción relacionada."),
    )
    last_transaction_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Monto de la última transacción asociada (en moneda original)."),
    )

    is_archived = models.BooleanField(
        default=False,
        help_text=_("Si está archivado, se oculta de la UI pero sigue activo contablemente."),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("owner", "name", "email")
        indexes = [
            models.Index(fields=["owner", "is_archived"]),
            models.Index(fields=["owner", "net_balance"]),
        ]
        verbose_name = _("Contacto")
        verbose_name_plural = _("Contactos")

    def __str__(self):
        return self.effective_name()

    def effective_name(self) -> str:
        return self.nickname or self.name

    # ------- Reglas de negocio -------

    def recalc_net_balance(self, commit: bool = True):
        """
        Recalcula el saldo neto con este contacto en base a los TransactionParticipant
        relacionados (solo los activos y de transacciones confirmadas).
        """
        from finance.transactions.Models.transacciones import TransactionParticipant

        qs = (
            TransactionParticipant.objects.filter(
                owner=self.owner,
                contact=self,
                status__in=[
                    TransactionParticipant.Status.ACTIVE,
                    TransactionParticipant.Status.PENDING,
                    TransactionParticipant.Status.PARTIAL,
                ],
                transaction__confirmed=True,
            )
            .select_related("transaction")
        )

        net = Decimal("0.00")
        last_tx_dt = None
        last_tx_amount = Decimal("0.00")

        for part in qs:
            tx = part.transaction
            amount = part.share_amount

            if part.direction == TransactionParticipant.Direction.USER_IS_CREDITOR:
                net += amount
            else:
                net -= amount

            tx_dt = tx.created_at
            if last_tx_dt is None or tx_dt > last_tx_dt:
                last_tx_dt = tx_dt
                last_tx_amount = amount

        self.net_balance = net
        self.last_transaction_at = last_tx_dt
        self.last_transaction_amount = last_tx_amount
        if last_tx_dt:
            self.last_activity_at = last_tx_dt

        if commit:
            self.save(
                update_fields=[
                    "net_balance",
                    "last_activity_at",
                    "last_transaction_at",
                    "last_transaction_amount",
                    "updated_at",
                ]
            )

        return self.net_balance
