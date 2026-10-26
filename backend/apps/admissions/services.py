from __future__ import annotations

import secrets
from typing import Any

from django.core.exceptions import ValidationError
from django.http import HttpRequest

from apps.academics.models import ClassArm
from apps.students.models import StudentGuardian
from apps.students.services import create_student
from control_plane.members import invite_member
from control_plane.models import Role
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from integrations.phone import normalize_gh_phone

from .models import Application


def _reference() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion when read aloud
    return "APP-" + "".join(secrets.choice(alphabet) for _ in range(8))


def submit_application(
    *, request: HttpRequest | None, data: dict[str, Any], source: str
) -> Application:
    phone = normalize_gh_phone(data.get("guardian_phone"))
    if not phone:
        raise ValidationError({"guardian_phone": "Enter a valid Ghanaian mobile number."})
    with tenant_atomic():
        application = Application(
            **{**data, "guardian_phone": phone}, source=source, reference=_reference()
        )
        application.full_clean()
        application.save()
        record_event(
            action="admission.submitted",
            request=request,
            target=application,
            after={"source": source, "reference": application.reference},
        )
    if source == Application.Source.ONLINE:
        from apps.communication.services import member_ids, notify_users

        notify_users(
            member_ids([Role.ADMIN, Role.PRINCIPAL]),
            kind="admission",
            title="New admission application",
            body=f"{application.first_name} {application.last_name} applied for "
            f"{application.desired_level}. Reference {application.reference}.",
            data={"application_id": str(application.pk)},
        )
    return application


def change_status(
    *, request: HttpRequest | None, application: Application, status: str, notes: str = ""
) -> Application:
    allowed = Application.TRANSITIONS.get(application.status, set())
    if status == Application.Status.ENROLLED:
        raise ValidationError("Use enrol to admit an applicant.")
    if status not in allowed:
        raise ValidationError(f"Can't move an application from {application.status} to {status}.")
    with tenant_atomic():
        before = application.status
        application.status = status
        if notes:
            application.review_notes = notes
        application.save(update_fields=["status", "review_notes", "updated_at"])
        record_event(
            action="admission.status_changed",
            request=request,
            target=application,
            before={"status": before},
            after={"status": status},
            reason=notes,
        )
    return application


def enrol(
    *,
    request: HttpRequest,
    application: Application,
    arm: ClassArm,
    granter_roles: frozenset[str],
    invite_guardian: bool = True,
) -> Application:
    if application.status != Application.Status.OFFERED:
        raise ValidationError("Only applicants who have been offered a place can be enrolled.")
    if arm.level_id != application.desired_level_id:
        raise ValidationError("Choose a class arm in the level the applicant applied for.")

    guardian_user_id = None
    if invite_guardian and application.guardian_email:
        membership = invite_member(
            request=request,
            tenant=require_tenant(),
            granter_roles=granter_roles,
            email=application.guardian_email,
            role=Role.PARENT,
            first_name=application.guardian_name.split(" ")[0],
            phone=application.guardian_phone,
        )
        guardian_user_id = membership.user_id

    with tenant_atomic():
        student = create_student(
            request=request,
            data={
                "first_name": application.first_name,
                "middle_name": application.middle_name,
                "last_name": application.last_name,
                "date_of_birth": application.date_of_birth,
                "gender": application.gender,
                "arm": arm,
                "address": application.address,
                "admitted_on": application.created_at.date(),
            },
        )
        StudentGuardian.objects.create(
            student=student,
            guardian_user_id=guardian_user_id,
            full_name=application.guardian_name,
            phone=application.guardian_phone,
            email=application.guardian_email,
            relationship=application.guardian_relationship,
            is_primary=True,
        )
        application.status = Application.Status.ENROLLED
        application.student_id = student.pk
        application.save(update_fields=["status", "student_id", "updated_at"])
        record_event(
            action="admission.enrolled",
            request=request,
            target=application,
            after={"student_id": str(student.pk), "arm": str(arm)},
        )
        from control_plane.developer import emit

        emit(
            "student.admitted",
            {
                "id": str(student.pk),
                "admission_number": student.admission_number,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "class": str(arm),
            },
        )
    return application
