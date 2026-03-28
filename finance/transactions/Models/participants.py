# transactions/Models/participants.py
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

User = get_user_model()


class TransactionParticipant(models.Model):
    """
    Representa la participación de un contacto en una transacción
    (gasto compartido, reembolso, favores entre amigos, roommates, etc.).

    Se usa para construir el tablero de contactos:
    - "Te debe $X"
    - "Debes $Y"
    - "Liquidado"
    """

    class Direction(models.TextChoices):
        USER_IS_CREDITOR = "user_creditor", _(
            "El contacto me debe (yo pagué por él/ella)."
        )
        USER_IS_DEBTOR = "user_debtor", _(
            "Yo le debo al contacto (él/ella pagó por mí)."
        )

    class Status(models.TextChoices):
        ACTIVE = "active", _("Activo")
        SETTLED = "settled", _("Liquidado")
        CANCELED = "canceled", _("Cancelado")

    class Role(models.TextChoices):
        MAIN_PAYER = "main_payer", _("Pagador principal")
        SHARED = "shared", _("Participante compartido")
        OBSERVER = "observer", _("Solo observador")
        GUARANTOR = "guarantor", _("Garante / aval")

    class InviteStatus(models.TextChoices):
        NOT_INVITED = "not_invited", _("No invitado")
        INVITED = "invited", _("Invitado")
        ACCEPTED = "accepted", _("Aceptó")
        REJECTED = "rejected", _("Rechazó")

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tx_participants",
        help_text=_("Usuario dueño del ledger (igual a transaction.owner)."),
    )

    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.CASCADE,
        related_name="participants",
        help_text=_("Transacción a la que pertenece esta participación."),
    )

    contact = models.ForeignKey(
        "contacts.Contact",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="participants",
        help_text=_("Contacto asociado, opcional si solo se guarda el nombre suelto."),
    )

    # Datos congelados para evitar que cambios futuros en el contacto
    # alteren el historial.
    display_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text=_("Nombre congelado para mostrar en el historial."),
    )
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True, null=True)

    direction = models.CharField(
        max_length=32,
        choices=Direction.choices,
        default=Direction.USER_IS_CREDITOR,
        help_text=_(
            "Define si el usuario es acreedor (le deben) o deudor (debe al contacto)."
        ),
    )

    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.SHARED,
        help_text=_("Rol del participante dentro del gasto compartido."),
    )

    share_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        help_text=_("Monto asociado a este contacto en esta transacción."),
    )

    paid_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_(
            "Monto ya pagado/liquidado de este share. El pendiente se calcula "
            "como share_amount - paid_amount."
        ),
    )

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    invite_status = models.CharField(
        max_length=16,
        choices=InviteStatus.choices,
        default=InviteStatus.NOT_INVITED,
        help_text=_(
            "Estado de la invitación si se envió correo/WhatsApp para que el "
            "contacto use la app."
        ),
    )

    linked_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="as_contact_participant",
        help_text=_(
            "Si el contacto finalmente se registró como usuario, se enlaza aquí "
            "para reconciliar identidades."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "contact"]),
            models.Index(fields=["contact", "status"]),
            models.Index(fields=["transaction"]),
            models.Index(fields=["owner", "direction"]),
        ]
        unique_together = ("transaction", "contact", "direction")

    def __str__(self):
        name = self.display_name or (self.contact and str(self.contact)) or "N/A"
        return f"{name} / {self.share_amount}"

    # --------- PROPERTIES ---------

    @property
    def pending_amount(self) -> Decimal:
        """
        Cuánto queda realmente pendiente de este share.
        Nunca negativo.
        """
        remaining = Decimal(self.share_amount) - Decimal(self.paid_amount or 0)
        if remaining < 0:
            return Decimal("0.00")
        return remaining.quantize(Decimal("0.01"))

    @property
    def is_settled(self) -> bool:
        return self.status == self.Status.SETTLED or self.pending_amount == 0

    # --------- MÉTODOS DE NEGOCIO ---------

    def mark_settled(self, commit: bool = True):
        """
        Marca esta participación como liquidada: paid = share, status=settled.
        """
        self.paid_amount = self.share_amount
        self.status = self.Status.SETTLED
        if commit:
            self.save(update_fields=["paid_amount", "status", "updated_at"])
