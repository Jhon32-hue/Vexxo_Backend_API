"""Transactional orchestration for completing a user's onboarding."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from identity.users.models import UserOnboardingProfile

User = get_user_model()


class OnboardingVersionConflict(Exception):
    def __init__(self, profile: UserOnboardingProfile):
        self.profile = profile
        super().__init__("The onboarding profile changed on another client.")


@dataclass(frozen=True)
class OnboardingCompletionResult:
    user: object
    profile: UserOnboardingProfile
    profile_changed: bool


PROFILE_FIELDS = (
    "registration_country",
    "age_range",
    "preferred_currencies",
    "income_sources",
    "employment_type",
    "finance_method",
    "monthly_income_range",
    "use_cases",
)


def _normalized_profile_data(validated_data: dict) -> dict:
    normalized = {field: validated_data[field] for field in PROFILE_FIELDS}
    normalized["preferred_currencies"] = list(dict.fromkeys(normalized["preferred_currencies"]))
    normalized["income_sources"] = sorted(set(normalized["income_sources"]))
    normalized["use_cases"] = sorted(set(normalized["use_cases"]))
    return normalized


@transaction.atomic
def complete_onboarding(*, user, validated_data: dict) -> OnboardingCompletionResult:
    locked_user = User.objects.select_for_update().get(pk=user.pk)
    profile = UserOnboardingProfile.objects.select_for_update().filter(user=locked_user).first()
    base_version = validated_data.get("base_version")
    if profile is not None and base_version is not None and profile.profile_version != base_version:
        raise OnboardingVersionConflict(profile)

    profile_data = _normalized_profile_data(validated_data)
    now = timezone.now()
    profile_changed = profile is None or any(getattr(profile, field) != value for field, value in profile_data.items())

    if profile is None:
        profile = UserOnboardingProfile(
            user=locked_user,
            **profile_data,
            questionnaire_version=UserOnboardingProfile.CURRENT_QUESTIONNAIRE_VERSION,
            profile_version=1,
            completed_at=now,
        )
        profile.full_clean()
        profile.save()
    elif profile_changed:
        for field, value in profile_data.items():
            setattr(profile, field, value)
        profile.questionnaire_version = UserOnboardingProfile.CURRENT_QUESTIONNAIRE_VERSION
        profile.profile_version += 1
        profile.completed_at = now
        profile.full_clean()
        profile.save(
            update_fields=[
                *PROFILE_FIELDS,
                "questionnaire_version",
                "profile_version",
                "completed_at",
                "updated_at",
            ]
        )

    user_updates = []
    preferred_currency = profile.preferred_currencies[0]
    for field, value in (
        ("preferred_currency", preferred_currency),
        ("locale", validated_data["locale"]),
        ("timezone_name", validated_data["timezone_name"]),
    ):
        if getattr(locked_user, field) != value:
            setattr(locked_user, field, value)
            user_updates.append(field)
    if not locked_user.onboarding_completed:
        locked_user.onboarding_completed = True
        user_updates.append("onboarding_completed")
    if user_updates:
        locked_user.save(update_fields=[*user_updates, "updated_at"])

    return OnboardingCompletionResult(
        user=locked_user,
        profile=profile,
        profile_changed=profile_changed,
    )
