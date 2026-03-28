"""
Modelos FX del dominio financiero.

Descripcion general:
- centraliza el catalogo de monedas soportadas
- define los proveedores posibles de tasas de cambio
- almacena snapshots historicos o actuales de conversion

Analisis detallado:
- este modulo no consulta APIs externas por si mismo; hoy su rol es persistir
  y validar la tasa una vez ya fue obtenida por otro proceso
- `observed_at` distingue el momento real de la tasa frente al momento en que
  el registro fue insertado, lo cual es clave para auditoria y reportes
- `provider` permite guardar snapshots de varias fuentes externas sin mezclarlos
- `metadata` deja espacio para payload crudo, precision, ids externos o flags
  de calidad sin deformar el esquema principal
- para conocer "la tasa actual", el backend deberia consultar el ultimo
  `ExchangeRate` activo por par y proveedor, ordenado por `observed_at`

Que se puede hacer despues:
- agregar jobs o servicios que consulten APIs de exchange y creen snapshots
- definir prioridad/fallback entre proveedores
- soportar conversion triangulada cuando no exista un par directo

La intencion es que toda conversion monetaria del backend use esta capa como
fuente de verdad, evitando logica de FX dispersa entre apps.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class Currency(models.TextChoices):
    # LATAM
    COP = "COP", _("Peso Colombiano")
    MXN = "MXN", _("Peso Mexicano")
    ARS = "ARS", _("Peso Argentino")
    CLP = "CLP", _("Peso Chileno")
    PEN = "PEN", _("Sol Peruano")
    BRL = "BRL", _("Real Brasileño")
    PYG = "PYG", _("Guaraní Paraguayo")
    UYU = "UYU", _("Peso Uruguayo")
    BOB = "BOB", _("Boliviano")
    CRC = "CRC", _("Colón Costarricense")
    GTQ = "GTQ", _("Quetzal Guatemalteco")
    DOP = "DOP", _("Peso Dominicano")
    HNL = "HNL", _("Lempira Hondureña")
    NIO = "NIO", _("Córdoba Nicaragüense")
    PAB = "PAB", _("Balboa Panameño")

    # GLOBALES
    USD = "USD", _("Dólar Americano")
    EUR = "EUR", _("Euro")
    GBP = "GBP", _("Libra Esterlina")
    CHF = "CHF", _("Franco Suizo")
    CAD = "CAD", _("Dólar Canadiense")
    AUD = "AUD", _("Dólar Australiano")
    NZD = "NZD", _("Dólar Neozelandés")
    JPY = "JPY", _("Yen Japonés")
    CNY = "CNY", _("Yuan Chino")
    INR = "INR", _("Rupia India")
    KRW = "KRW", _("Won Surcoreano")
    SGD = "SGD", _("Dólar de Singapur")
    HKD = "HKD", _("Dólar de Hong Kong")
    AED = "AED", _("Dirham de Emiratos Árabes Unidos")
    SAR = "SAR", _("Riyal Saudí")

    # CRIPTO / ESTABLES
    BTC = "BTC", _("Bitcoin")
    ETH = "ETH", _("Ethereum")
    USDT = "USDT", _("Tether")
    USDC = "USDC", _("USD Coin")


class ExchangeRateProvider(models.TextChoices):
    MANUAL = "manual", _("Manual")
    ECB = "ecb", _("European Central Bank")
    OPEN_EXCHANGE = "open_exchange", _("Open Exchange")
    EXCHANGERATE_HOST = "exchangerate_host", _("ExchangeRate Host")
    BINANCE = "binance", _("Binance")
    CUSTOM = "custom", _("Custom")


class ExchangeRate(models.Model):
    """
    Tasa de cambio histórica / actual.
    Fuente única del backend para conversiones monetarias.
    """

    base_currency = models.CharField(
        max_length=10,
        choices=Currency.choices,
        db_index=True,
    )
    quote_currency = models.CharField(
        max_length=10,
        choices=Currency.choices,
        db_index=True,
    )
    rate = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        validators=[MinValueValidator(Decimal("0.00000001"))],
        help_text=_("1 unidad de base_currency equivale a 'rate' unidades de quote_currency."),
    )

    provider = models.CharField(
        max_length=32,
        choices=ExchangeRateProvider.choices,
        default=ExchangeRateProvider.MANUAL,
        db_index=True,
    )

    observed_at = models.DateTimeField(
        db_index=True,
        help_text=_("Momento exacto al que corresponde esta tasa."),
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_("Permite marcar tasas obsoletas o inválidas sin borrarlas."),
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Payload opcional del proveedor externo, fuente, precision, etc."),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-observed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["base_currency", "quote_currency", "provider", "observed_at"],
                name="unique_exchange_rate_snapshot",
            )
        ]
        indexes = [
            models.Index(fields=["base_currency", "quote_currency", "-observed_at"]),
            models.Index(fields=["provider", "-observed_at"]),
        ]
        verbose_name = _("Tasa de cambio")
        verbose_name_plural = _("Tasas de cambio")

    def __str__(self) -> str:
        return f"1 {self.base_currency} = {self.rate} {self.quote_currency} @ {self.observed_at}"

    def clean(self):
        super().clean()
        if self.base_currency == self.quote_currency:
            raise ValidationError(
                {"quote_currency": _("La moneda base y la moneda cotizada no pueden ser iguales.")}
            )

    @property
    def pair(self) -> str:
        return f"{self.base_currency}/{self.quote_currency}"
