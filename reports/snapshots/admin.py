from django.contrib import admin

from reports.snapshots.models import ReportSnapshot


@admin.register(ReportSnapshot)
class ReportSnapshotAdmin(admin.ModelAdmin):
    list_display = ("owner", "report_type", "period_start", "period_end", "currency", "generation_version", "created_at")
    list_filter = ("report_type", "currency")
    search_fields = ("owner__email", "owner__username", "payload_sha256", "idempotency_key")
    readonly_fields = [field.name for field in ReportSnapshot._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
