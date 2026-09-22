from django.contrib import admin

from reports.monthly_reports.models import MonthlyReportClose


@admin.register(MonthlyReportClose)
class MonthlyReportCloseAdmin(admin.ModelAdmin):
    list_display = ("owner", "period_start", "currency", "version", "status", "is_current", "closed_at")
    list_filter = ("currency", "status", "is_current")
    search_fields = ("owner__email", "owner__username")
    readonly_fields = ("created_at", "closed_at")
