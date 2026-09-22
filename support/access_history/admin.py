from django.contrib import admin

from support.access_history.models import SupportAccessRecord


@admin.register(SupportAccessRecord)
class SupportAccessRecordAdmin(admin.ModelAdmin):
    list_display = ("created_at", "staff_user", "subject_user", "module", "target_type", "case_reference")
    list_filter = ("module", "action")
    search_fields = ("staff_user__email", "subject_user__email", "target_id", "case_reference")
    readonly_fields = [field.name for field in SupportAccessRecord._meta.fields]
