from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from .models import ClassArm, Subject, TeachingAssignment


def arms_taught_by(user: Any) -> QuerySet[ClassArm]:
    return ClassArm.objects.filter(assignments__teacher_user_id=user.pk).distinct()


def teaches_arm(user: Any, arm_id: Any) -> bool:
    return TeachingAssignment.objects.filter(teacher_user_id=user.pk, arm_id=arm_id).exists()


def teaches_subject(user: Any, arm_id: Any, subject_id: Any) -> bool:
    return TeachingAssignment.objects.filter(
        teacher_user_id=user.pk, arm_id=arm_id, subject_id=subject_id
    ).exists()


def is_form_teacher(user: Any, arm_id: Any) -> bool:
    return TeachingAssignment.objects.filter(
        teacher_user_id=user.pk, arm_id=arm_id, is_form_teacher=True
    ).exists()


def subjects_for_arm(arm: ClassArm) -> QuerySet[Subject]:
    """Subjects offered at this arm's section that are actually assigned to a teacher."""
    return Subject.objects.filter(assignments__arm=arm, is_active=True).distinct().order_by("name")
