from django.contrib import admin

from tasks.scheduled.models import ScheduledJobState


@admin.register(ScheduledJobState)
class ScheduledJobStateAdmin(admin.ModelAdmin):
    list_display = (
        "job_name",
        "status",
        "run_count",
        "failure_count",
        "last_succeeded_at",
        "next_run_at",
    )
    list_filter = ("status",)
    search_fields = ("job_name", "last_error")
    readonly_fields = [field.name for field in ScheduledJobState._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
