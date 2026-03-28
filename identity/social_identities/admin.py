from django.contrib import admin

from identity.social_identities.models import SocialAuthHandoff, UserSocialIdentity


@admin.register(UserSocialIdentity)
class UserSocialIdentityAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "provider", "provider_user_id", "email", "is_active", "linked_at", "last_login_at")
    list_filter = ("provider", "is_active", "email_verified")
    search_fields = ("provider_user_id", "email", "user__email", "user__username")


@admin.register(SocialAuthHandoff)
class SocialAuthHandoffAdmin(admin.ModelAdmin):
    list_display = ("code", "provider", "user", "login_mode", "created_user", "linked_identity", "expires_at", "used_at")
    list_filter = ("provider", "login_mode", "created_user", "linked_identity")
    search_fields = ("code", "user__email", "user__username")
