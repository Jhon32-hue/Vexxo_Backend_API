"""Validated API contracts for the post-registration onboarding flow."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.validators import RegexValidator
from rest_framework import serializers

from finance.fx.models import Currency
from identity.users.models.onboarding import (
    AgeRange,
    EmploymentType,
    FinanceMethod,
    INCOME_SOURCE_CODES,
    MonthlyIncomeRange,
    RegistrationCountry,
    USE_CASE_CODES,
    UserOnboardingProfile,
)


class UniqueChoiceListField(serializers.ListField):
    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        if len(values) != len(set(values)):
            raise serializers.ValidationError("No se permiten valores duplicados.")
        return values


class CompleteOnboardingSerializer(serializers.Serializer):
    registration_country = serializers.ChoiceField(choices=RegistrationCountry.choices)
    age_range = serializers.ChoiceField(choices=AgeRange.choices)
    preferred_currencies = UniqueChoiceListField(
        child=serializers.ChoiceField(choices=Currency.choices),
        min_length=1,
        max_length=8,
    )
    income_sources = UniqueChoiceListField(
        child=serializers.ChoiceField(choices=sorted(INCOME_SOURCE_CODES)),
        min_length=1,
        max_length=8,
    )
    employment_type = serializers.ChoiceField(choices=EmploymentType.choices)
    finance_method = serializers.ChoiceField(choices=FinanceMethod.choices)
    monthly_income_range = serializers.ChoiceField(choices=MonthlyIncomeRange.choices)
    use_cases = UniqueChoiceListField(
        child=serializers.ChoiceField(choices=sorted(USE_CASE_CODES)),
        min_length=1,
        max_length=8,
    )
    locale = serializers.CharField(
        max_length=16,
        validators=[RegexValidator(r"^[a-z]{2}(?:_[A-Z]{2})?$", "Locale invalido.")],
    )
    timezone_name = serializers.CharField(max_length=64)
    base_version = serializers.IntegerField(min_value=1, required=False)

    def validate_timezone_name(self, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise serializers.ValidationError("Zona horaria invalida.") from exc
        return value


class UserOnboardingProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserOnboardingProfile
        fields = [
            "registration_country",
            "age_range",
            "preferred_currencies",
            "income_sources",
            "employment_type",
            "finance_method",
            "monthly_income_range",
            "use_cases",
            "questionnaire_version",
            "profile_version",
            "completed_at",
            "updated_at",
        ]
        read_only_fields = fields
