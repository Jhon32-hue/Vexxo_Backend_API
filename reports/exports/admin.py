from django.contrib import admin

from reports.exports.models import ReportExport


@admin.register(ReportExport)
class ReportExportAdmin(admin.ModelAdmin):
    list_display = ("owner", "export_format", "status", "expires_at", "content_purged_at", "legal_hold")
    list_filter = ("export_format", "status", "legal_hold")
    search_fields = ("owner__email", "owner__username", "plaintext_sha256")
    readonly_fields = (
        "encrypted_content",
        "encryption_envelope",
        "download_token_hash",
        "plaintext_sha256",
        "created_at",
        "updated_at",
    )
