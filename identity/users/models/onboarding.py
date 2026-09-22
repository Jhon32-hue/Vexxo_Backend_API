"""Structured, versioned onboarding profile owned by identity."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from finance.fx.models import Currency
from security.validators import validate_safe_metadata


class RegistrationCountry(models.TextChoices):
    COLOMBIA = "CO", _("Colombia")
    MEXICO = "MX", _("Mexico")
    ARGENTINA = "AR", _("Argentina")
    CHILE = "CL", _("Chile")
    PERU = "PE", _("Peru")
    BRAZIL = "BR", _("Brasil")
    UNITED_STATES = "US", _("Estados Unidos")
    SPAIN = "ES", _("Espana")


class AgeRange(models.TextChoices):
    AGE_18_24 = "18_24", _("18 a 24")
    AGE_25_34 = "25_34", _("25 a 34")
    AGE_35_44 = "35_44", _("35 a 44")
    AGE_45_54 = "45_54", _("45 a 54")
    AGE_55_64 = "55_64", _("55 a 64")
    AGE_65_PLUS = "65_plus", _("65 o mas")


class EmploymentType(models.TextChoices):
    EMPLOYEE = "employee", _("Empleado")
    INDEPENDENT = "independent", _("Independiente")
    FREELANCER = "freelancer", _("Freelancer")
    ENTREPRENEUR = "entrepreneur", _("Emprendedor")
    STUDENT = "student", _("Estudiante")
    RETIRED = "retired", _("Retirado")
    UNEMPLOYED = "unemployed", _("Sin empleo")
    INVESTOR = "investor", _("Inversionista")


class FinanceMethod(models.TextChoices):
    EXCEL = "excel", _("Excel")
    PAPER = "paper", _("Papel")
    OTHER_APPS = "other_apps", _("Otras aplicaciones")
    BANK_APP = "bank_app", _("Aplicacion bancaria")
    NONE = "none", _("Ninguno")


class MonthlyIncomeRange(models.TextChoices):
    LESS_THAN_1M = "less_than_1m", _("Menos de 1M COP")
    FROM_1M_TO_3M = "1m_3m", _("1M a 3M COP")
    FROM_3M_TO_6M = "3m_6m", _("3M a 6M COP")
    FROM_6M_TO_10M = "6m_10m", _("6M a 10M COP")
    FROM_10M_TO_20M = "10m_20m", _("10M a 20M COP")
    MORE_THAN_20M = "more_than_20m", _("Mas de 20M COP")


INCOME_SOURCE_CODES = frozenset(
    {
        "salary",
        "freelance",
        "independent_business",
        "investments",
        "inheritance",
        "savings",
        "family_support",
        "other",
    }
)

USE_CASE_CODES = frozenset(
    {
        "track_expenses",
        "shared_expenses",
        "save_goals",
        "convert_money",
        "receive_foreign_currency",
        "investing",
        "scheduled_payments",
        "ocr_receipts",
    }
)


def _validate_code_list(value, *, allowed: set[str] | frozenset[str], field_name: str, max_items: int) -> None:
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{field_name} must be a non-empty list.")
    if len(value) > max_items:
        raise ValidationError(f"{field_name} accepts at most {max_items} values.")
    if any(not isinstance(item, str) or item not in allowed for item in value):
        raise ValidationError(f"{field_name} contains an unsupported value.")
    if len(value) != len(set(value)):
        raise ValidationError(f"{field_name} cannot contain duplicates.")


def validate_preferred_currencies(value) -> None:
    _validate_code_list(value, allowed=set(Currency.values), field_name="preferred_currencies", max_items=8)


def validate_income_sources(value) -> None:
    _validate_code_list(value, allowed=INCOME_SOURCE_CODES, field_name="income_sources", max_items=8)


def validate_use_cases(value) -> None:
    _validate_code_list(value, allowed=USE_CASE_CODES, field_name="use_cases", max_items=8)


class UserOnboardingProfile(models.Model):
    """Confidential product-personalization data captured after registration."""

    CURRENT_QUESTIONNAIRE_VERSION = 2

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="onboarding_profile",
    )
    registration_country = models.CharField(max_length=2, choices=RegistrationCountry.choices)
    age_range = models.CharField(max_length=16, choices=AgeRange.choices)
    preferred_currencies = models.JSONField(
        default=list,
        validators=[validate_safe_metadata, validate_preferred_currencies],
    )
    income_sources = models.JSONField(
        default=list,
        validators=[validate_safe_metadata, validate_income_sources],
    )
    employment_type = models.CharField(max_length=24, choices=EmploymentType.choices)
    finance_method = models.CharField(max_length=24, choices=FinanceMethod.choices)
    monthly_income_range = models.CharField(max_length=24, choices=MonthlyIncomeRange.choices)
    use_cases = models.JSONField(
        default=list,
        validators=[validate_safe_metadata, validate_use_cases],
    )
    questionnaire_version = models.PositiveSmallIntegerField(default=CURRENT_QUESTIONNAIRE_VERSION)
    profile_version = models.PositiveIntegerField(default=1)
    completed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Perfil de onboarding")
        verbose_name_plural = _("Perfiles de onboarding")
        indexes = [
            models.Index(fields=["registration_country", "created_at"]),
            models.Index(fields=["questionnaire_version", "updated_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(profile_version__gte=1),
                name="user_onboarding_profile_version_positive",
            )
        ]

    def __str__(self) -> str:
        return f"onboarding:{self.user_id}:v{self.profile_version}"
