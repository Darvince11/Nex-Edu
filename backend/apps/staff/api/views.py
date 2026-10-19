from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import QuerySet
from rest_framework import serializers

from apps.academics.api.views import AuditedCrudViewSet
from core.permissions import has_perm
from core.rbac import Perm

from ..models import StaffProfile


class StaffSerializer(serializers.ModelSerializer[StaffProfile]):
    class Meta:
        model = StaffProfile
        fields: ClassVar = [
            "id",
            "user_id",
            "staff_number",
            "first_name",
            "last_name",
            "gender",
            "phone",
            "email",
            "job_title",
            "qualification",
            "employment_date",
            "is_active",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar = ["created_at", "updated_at"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is None or not has_perm(request, Perm.STAFF_MANAGE):
            for name in ("bank_name", "bank_account_name", "bank_account_number"):
                self.fields.pop(name, None)


class StaffViewSet(AuditedCrudViewSet):
    serializer_class = StaffSerializer
    audit_name = "staff.profile"
    required_permissions: ClassVar = {
        "list": Perm.STAFF_VIEW,
        "retrieve": Perm.STAFF_VIEW,
        "create": Perm.STAFF_MANAGE,
        "update": Perm.STAFF_MANAGE,
        "partial_update": Perm.STAFF_MANAGE,
        "destroy": Perm.STAFF_MANAGE,
    }

    def get_queryset(self) -> QuerySet[StaffProfile]:
        qs = StaffProfile.objects.all()
        if self.request.query_params.get("active") == "1":
            qs = qs.filter(is_active=True)
        return qs
