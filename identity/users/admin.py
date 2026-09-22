"""Django admin registrations for identity users."""

from django.contrib import admin

from identity.users.models import UserOnboardingProfile


@admin.register(UserOnboardingProfile)
class UserOnboardingProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "registration_country",
        "questionnaire_version",
        "profile_version",
        "completed_at",
    )
    list_filter = ("registration_country", "questionnaire_version", "employment_type")
    search_fields = ("user__email", "user__username")
    readonly_fields = ("questionnaire_version", "profile_version", "completed_at", "created_at", "updated_at")
