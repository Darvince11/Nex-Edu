"""Which students a user may see. The only place that builds student querysets for the API.

Visibility is the union over the user's roles in this school:
- school-wide roles (owner, principal, admin, bursar, ...): every student
- teacher / form teacher: students in arms they are assigned to
- parent: their linked children
- student: themselves
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db.models import Q, QuerySet

from apps.academics.models import TeachingAssignment
from control_plane.models import Role
from control_plane.tenancy import require_tenant
from core.crypto import blind_index
from core.rbac import SCHOOL_WIDE_STUDENT_ROLES

from .models import Student


def visible_students(user: Any, roles: Iterable[str]) -> QuerySet[Student]:
    roles = set(roles)
    queryset = Student.objects.select_related("arm__level")
    if roles & SCHOOL_WIDE_STUDENT_ROLES:
        return queryset.all()

    condition = Q(pk__in=[])
    if roles & {Role.TEACHER, Role.FORM_TEACHER}:
        arm_ids = TeachingAssignment.objects.filter(teacher_user_id=user.pk).values("arm_id")
        condition |= Q(arm_id__in=arm_ids)
    if Role.PARENT in roles:
        condition |= Q(guardians__guardian_user_id=user.pk)
    if Role.STUDENT in roles:
        condition |= Q(user_id=user.pk)
    return queryset.filter(condition).distinct()


def find_by_national_id(number: str) -> Student | None:
    index = blind_index(number, tenant=require_tenant(), context="students.student.national_id")
    return Student.objects.filter(national_id_bidx=index).first()
