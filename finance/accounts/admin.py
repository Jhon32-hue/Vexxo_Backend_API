"""
Admin del modulo accounts.

Descripcion general:
- registra modelos operativos del dominio para soporte, auditoria y backoffice

Analisis detallado:
- aunque la operacion principal de Vexxo vive en API y workers, tener un admin
  razonable acelera soporte, debugging y revision de incidentes
"""

from django.contrib import admin

from finance.accounts.models import Account, AccountMembership, BalanceSnapshot, DomainEventOutbox


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "owner",
        "type",
        "currency",
        "status",
        "sync_status",
        "provider",
        "is_primary",
        "updated_at",
    )
    list_filter = ("type", "currency", "status", "sync_status", "provider", "is_primary")
    search_fields = ("name", "owner__username", "owner__email", "external_id", "institution")
    readonly_fields = ("created_at", "updated_at", "last_sync_at", "last_sync_status_at")


@admin.register(AccountMembership)
class AccountMembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "account", "user", "role", "access_mode", "is_active", "accepted_at", "revoked_at")
    list_filter = ("role", "access_mode", "is_active")
    search_fields = ("account__name", "user__username", "user__email")
    readonly_fields = ("invitation_token",)


@admin.register(BalanceSnapshot)
class BalanceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "account", "as_of", "drift", "drift_abs", "is_consistent", "source", "created_at")
    list_filter = ("is_consistent", "source")
    search_fields = ("account__name", "account__owner__username")


@admin.register(DomainEventOutbox)
class DomainEventOutboxAdmin(admin.ModelAdmin):
    list_display = ("id", "aggregate_type", "aggregate_id", "event_type", "status", "retry_count", "occurred_at")
    list_filter = ("aggregate_type", "status", "event_type")
    search_fields = ("aggregate_id", "idempotency_key", "event_type", "locked_by")
    readonly_fields = ("id", "occurred_at", "published_at")
