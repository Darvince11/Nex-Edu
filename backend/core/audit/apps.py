from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = "core.audit"
    label = "audit"
    verbose_name = "Audit log"
