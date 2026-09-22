from django.apps import AppConfig


class AuditTrailsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'admin_tools.audit_trails'
    label = 'admin_audit_trails'
