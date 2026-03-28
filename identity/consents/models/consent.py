"""
Consentimientos y autorizaciones del usuario.

Descripcion general:
- registra consentimientos legales, comerciales y de datos del usuario
- sirve como base para open banking, data sharing y trazabilidad regulatoria

Analisis detallado:
- no todos los consentimientos son iguales: unos son legales generales
  (terminos, privacidad), otros son regulatorios o de integracion
  (open banking, data sharing, OCR, AI)
- este modelo permite versionar el texto aceptado, el alcance, el proveedor
  implicado y la fecha de expiracion/revocacion
- tambien puede enlazarse con IDs externos de consentimiento emitidos por un
  proveedor de open finance
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class ConsentType(models.TextChoices):
    TERMS = "terms", "Terms"
    PRIVACY = "privacy", "Privacy"
    MARKETING = "marketing", "Marketing"
    OPEN_BANKING_DATA = "open_banking_data", "Open Banking Data"
    OPEN_BANKING_PAYMENTS = "open_banking_payments", "Open Banking Payments"
    DATA_EXPORT = "data_export", "Data Export"
    DOCUMENT_OCR = "document_ocr", "Document OCR"
    AI_PROCESSING = "ai_processing", "AI Processing"


class ConsentStatus(models.TextChoices):
    GRANTED = "granted", "Granted"
    REVOKED = "revoked", "Revoked"
    EXPIRED = "expired", "Expired"
    PENDING = "pending", "Pending"


class UserConsent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="identity_consents",
    )
    consent_type = models.CharField(max_length=32, choices=ConsentType.choices)
    provider = models.CharField(max_length=64, blank=True, default="")
    external_consent_id = models.CharField(max_length=128, blank=True, default="")
    scope_code = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=16, choices=ConsentStatus.choices, default=ConsentStatus.PENDING)
    purpose = models.CharField(max_length=255, blank=True, default="")
    legal_basis = models.CharField(max_length=64, blank=True, default="")
    terms_version = models.CharField(max_length=32, blank=True, default="")
    privacy_version = models.CharField(max_length=32, blank=True, default="")
    granted_at = models.DateTimeField(blank=True, null=True)
    revoked_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    granted_via = models.CharField(max_length=32, blank=True, default="")
    data_categories = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "consent_type", "status"]),
            models.Index(fields=["provider", "external_consent_id"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.consent_type}:{self.status}"

    def grant(self, *, commit: bool = True) -> None:
        self.status = ConsentStatus.GRANTED
        if self.granted_at is None:
            self.granted_at = timezone.now()
        if commit:
            self.save(update_fields=["status", "granted_at", "updated_at"])

    def revoke(self, *, commit: bool = True) -> None:
        self.status = ConsentStatus.REVOKED
        self.revoked_at = timezone.now()
        if commit:
            self.save(update_fields=["status", "revoked_at", "updated_at"])

    def mark_expired(self, *, commit: bool = True) -> None:
        self.status = ConsentStatus.EXPIRED
        if commit:
            self.save(update_fields=["status", "updated_at"])
